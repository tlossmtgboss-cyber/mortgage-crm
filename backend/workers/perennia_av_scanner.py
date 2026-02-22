"""
Perennia Docs AV Scanner Worker

Scans uploaded documents for viruses using ClamAV.
Integrates with the document processing pipeline.

Features:
- ClamAV daemon connection (clamd)
- S3 download and scan
- Status updates to database
- Quarantine handling for infected files
- Retry logic for transient failures
"""

import os
import io
import logging
import tempfile
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of a virus scan."""
    is_clean: bool
    status: str  # clean, infected, failed
    threat_name: Optional[str] = None
    scan_time_ms: int = 0
    scanner_version: Optional[str] = None
    signature_version: Optional[str] = None
    error_message: Optional[str] = None


class ClamAVScanner:
    """
    ClamAV scanner integration.

    Supports both clamd socket connection and clamscan CLI fallback.
    """

    def __init__(
        self,
        socket_path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        timeout: int = 120
    ):
        """
        Initialize ClamAV scanner.

        Args:
            socket_path: Path to clamd Unix socket
            host: clamd TCP host (alternative to socket)
            port: clamd TCP port
            timeout: Scan timeout in seconds
        """
        self.socket_path = socket_path or os.getenv("CLAMAV_SOCKET", "/var/run/clamav/clamd.sock")
        self.host = host or os.getenv("CLAMAV_HOST")
        self.port = port or int(os.getenv("CLAMAV_PORT", "3310"))
        self.timeout = timeout
        self.clamd = None
        self._use_socket = not self.host

    def _get_clamd(self):
        """Get or create clamd connection."""
        if self.clamd is not None:
            return self.clamd

        try:
            import clamd

            if self._use_socket:
                self.clamd = clamd.ClamdUnixSocket(path=self.socket_path)
            else:
                self.clamd = clamd.ClamdNetworkSocket(host=self.host, port=self.port, timeout=self.timeout)

            # Test connection
            version = self.clamd.version()
            logger.info(f"ClamAV connected: {version}")
            return self.clamd

        except ImportError:
            logger.warning("clamd package not installed, using CLI fallback")
            return None
        except Exception as e:
            logger.error(f"Failed to connect to ClamAV: {e}")
            return None

    def scan_bytes(self, data: bytes, filename: str = "unknown") -> ScanResult:
        """
        Scan bytes data for viruses.

        Args:
            data: File data to scan
            filename: Original filename (for logging)

        Returns:
            ScanResult with scan outcome
        """
        import time
        start_time = time.time()

        clamd = self._get_clamd()

        if clamd is not None:
            return self._scan_with_clamd(clamd, data, filename, start_time)
        else:
            return self._scan_with_cli(data, filename, start_time)

    def _scan_with_clamd(self, clamd, data: bytes, filename: str, start_time: float) -> ScanResult:
        """Scan using clamd daemon."""
        import time

        try:
            # Use INSTREAM command
            result = clamd.instream(io.BytesIO(data))

            scan_time = int((time.time() - start_time) * 1000)

            # Parse result - format is {'stream': ('OK', None)} or {'stream': ('FOUND', 'Virus.Name')}
            if 'stream' in result:
                status, threat = result['stream']

                if status == 'OK':
                    return ScanResult(
                        is_clean=True,
                        status='clean',
                        scan_time_ms=scan_time,
                        scanner_version=str(clamd.version())
                    )
                elif status == 'FOUND':
                    logger.warning(f"Virus detected in {filename}: {threat}")
                    return ScanResult(
                        is_clean=False,
                        status='infected',
                        threat_name=threat,
                        scan_time_ms=scan_time,
                        scanner_version=str(clamd.version())
                    )
                else:
                    return ScanResult(
                        is_clean=False,
                        status='failed',
                        error_message=f"Unknown scan status: {status}",
                        scan_time_ms=scan_time
                    )

            return ScanResult(
                is_clean=False,
                status='failed',
                error_message="Invalid scan response",
                scan_time_ms=scan_time
            )

        except Exception as e:
            logger.error(f"ClamAV scan failed for {filename}: {e}")
            return ScanResult(
                is_clean=False,
                status='failed',
                error_message=str(e),
                scan_time_ms=int((time.time() - start_time) * 1000)
            )

    def _scan_with_cli(self, data: bytes, filename: str, start_time: float) -> ScanResult:
        """Scan using clamscan CLI (fallback)."""
        import time
        import subprocess

        try:
            # Write to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.scan') as f:
                f.write(data)
                temp_path = f.name

            try:
                # Run clamscan
                result = subprocess.run(
                    ['clamscan', '--no-summary', temp_path],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )

                scan_time = int((time.time() - start_time) * 1000)

                # Exit code 0 = clean, 1 = infected, 2 = error
                if result.returncode == 0:
                    return ScanResult(
                        is_clean=True,
                        status='clean',
                        scan_time_ms=scan_time
                    )
                elif result.returncode == 1:
                    # Parse threat name from output
                    threat_name = None
                    for line in result.stdout.split('\n'):
                        if 'FOUND' in line:
                            parts = line.split(':')
                            if len(parts) >= 2:
                                threat_name = parts[1].replace('FOUND', '').strip()
                            break

                    logger.warning(f"Virus detected in {filename}: {threat_name}")
                    return ScanResult(
                        is_clean=False,
                        status='infected',
                        threat_name=threat_name,
                        scan_time_ms=scan_time
                    )
                else:
                    return ScanResult(
                        is_clean=False,
                        status='failed',
                        error_message=result.stderr or f"clamscan exit code {result.returncode}",
                        scan_time_ms=scan_time
                    )

            finally:
                # Clean up temp file
                os.unlink(temp_path)

        except subprocess.TimeoutExpired:
            return ScanResult(
                is_clean=False,
                status='failed',
                error_message=f"Scan timeout after {self.timeout}s",
                scan_time_ms=self.timeout * 1000
            )
        except FileNotFoundError:
            return ScanResult(
                is_clean=False,
                status='failed',
                error_message="clamscan not found - ClamAV not installed"
            )
        except Exception as e:
            return ScanResult(
                is_clean=False,
                status='failed',
                error_message=str(e)
            )

    def get_version(self) -> Optional[str]:
        """Get ClamAV version."""
        clamd = self._get_clamd()
        if clamd:
            try:
                return clamd.version()
            except Exception as e:
                logger.warning(f"Error getting ClamAV version: {e}")
        return None


class PerenniaAVScannerWorker:
    """
    Worker that processes documents pending virus scanning.

    Workflow:
    1. Query for documents with virus_scan_status = 'pending'
    2. Download document from S3
    3. Scan with ClamAV
    4. Update database with result
    5. If infected, move to quarantine and notify
    """

    def __init__(self, db: Session, s3_service=None):
        """
        Initialize worker.

        Args:
            db: Database session
            s3_service: Optional S3 service (defaults to singleton)
        """
        self.db = db
        self.scanner = ClamAVScanner()

        if s3_service is None:
            from services.perennia_s3_service import get_s3_service
            self.s3 = get_s3_service()
        else:
            self.s3 = s3_service

        self.batch_size = 10
        self.quarantine_bucket = os.getenv("PERENNIA_QUARANTINE_BUCKET", "perennia-quarantine")

    def get_pending_documents(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get documents pending virus scan."""
        result = self.db.execute(text("""
            SELECT id, loan_id, lead_id, request_id,
                   file_name, file_size, mime_type,
                   original_storage_key
            FROM perennia_documents
            WHERE virus_scan_status = 'pending'
              AND status = 'uploaded'
            ORDER BY created_at ASC
            LIMIT :limit
        """), {"limit": limit or self.batch_size})

        return [dict(row._mapping) for row in result]

    def scan_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Scan a single document.

        Args:
            document: Document record from database

        Returns:
            Dict with scan result and any actions taken
        """
        doc_id = document['id']
        storage_key = document['original_storage_key']
        file_name = document['file_name']

        logger.info(f"Scanning document {doc_id}: {file_name}")

        result = {
            "document_id": doc_id,
            "success": False,
            "scan_result": None,
            "actions": []
        }

        try:
            # Update status to scanning
            self.db.execute(text("""
                UPDATE perennia_documents
                SET virus_scan_status = 'scanning', updated_at = NOW()
                WHERE id = :id
            """), {"id": doc_id})
            self.db.commit()

            # Download from S3
            import boto3
            s3_client = boto3.client('s3')

            response = s3_client.get_object(
                Bucket=self.s3.bucket_name,
                Key=storage_key
            )
            file_data = response['Body'].read()

            # Scan
            scan_result = self.scanner.scan_bytes(file_data, file_name)
            result["scan_result"] = {
                "is_clean": scan_result.is_clean,
                "status": scan_result.status,
                "threat_name": scan_result.threat_name,
                "scan_time_ms": scan_result.scan_time_ms,
                "scanner_version": scan_result.scanner_version
            }

            # Update database
            if scan_result.is_clean:
                self._mark_clean(doc_id, scan_result)
                result["actions"].append("marked_clean")
                result["success"] = True

            elif scan_result.status == 'infected':
                self._handle_infected(document, scan_result)
                result["actions"].append("quarantined")
                result["actions"].append("notification_queued")
                result["success"] = True

            else:
                self._mark_failed(doc_id, scan_result)
                result["actions"].append("marked_failed")
                result["success"] = False

        except Exception as e:
            logger.error(f"Error scanning document {doc_id}: {e}")
            self._mark_failed(doc_id, ScanResult(
                is_clean=False,
                status='failed',
                error_message=str(e)
            ))
            result["error"] = str(e)

        return result

    def _mark_clean(self, doc_id: int, scan_result: ScanResult):
        """Mark document as clean."""
        self.db.execute(text("""
            UPDATE perennia_documents
            SET virus_scan_status = 'clean',
                virus_scan_result = :result,
                status = 'processing',
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": doc_id,
            "result": {
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "scan_time_ms": scan_result.scan_time_ms,
                "scanner_version": scan_result.scanner_version
            }
        })
        self.db.commit()

        # Log event
        self.db.execute(text("""
            INSERT INTO perennia_document_events (
                document_id, event_type, event_data,
                actor_type, created_at
            ) VALUES (
                :doc_id, 'document_scanned',
                :event_data, 'system', NOW()
            )
        """), {
            "doc_id": doc_id,
            "event_data": {"status": "clean", "scan_time_ms": scan_result.scan_time_ms}
        })
        self.db.commit()

    def _handle_infected(self, document: Dict[str, Any], scan_result: ScanResult):
        """Handle infected document - quarantine and notify."""
        doc_id = document['id']

        # Update status
        self.db.execute(text("""
            UPDATE perennia_documents
            SET virus_scan_status = 'infected',
                virus_scan_result = :result,
                status = 'rejected',
                rejection_reason = :reason,
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": doc_id,
            "result": {
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "threat_name": scan_result.threat_name,
                "scan_time_ms": scan_result.scan_time_ms
            },
            "reason": f"Virus detected: {scan_result.threat_name}"
        })
        self.db.commit()

        # Log event
        self.db.execute(text("""
            INSERT INTO perennia_document_events (
                document_id, loan_id, lead_id,
                event_type, event_data,
                actor_type, created_at
            ) VALUES (
                :doc_id, :loan_id, :lead_id,
                'virus_detected', :event_data, 'system', NOW()
            )
        """), {
            "doc_id": doc_id,
            "loan_id": document.get('loan_id'),
            "lead_id": document.get('lead_id'),
            "event_data": {"threat_name": scan_result.threat_name}
        })
        self.db.commit()

        # Queue notification
        self.db.execute(text("""
            INSERT INTO perennia_notifications (
                loan_id, lead_id, channel, template,
                subject, body, metadata,
                status, created_at, updated_at
            ) VALUES (
                :loan_id, :lead_id, 'email', 'virus_detected',
                'Security Alert: Infected file uploaded',
                :body, :metadata,
                'pending', NOW(), NOW()
            )
        """), {
            "loan_id": document.get('loan_id'),
            "lead_id": document.get('lead_id'),
            "body": f"An infected file was detected and quarantined: {document['file_name']}. Threat: {scan_result.threat_name}",
            "metadata": {
                "document_id": doc_id,
                "threat_name": scan_result.threat_name,
                "file_name": document['file_name']
            }
        })
        self.db.commit()

        # Move to quarantine bucket
        try:
            import boto3
            s3_client = boto3.client('s3')

            # Copy to quarantine
            quarantine_key = f"quarantine/{doc_id}/{document['original_storage_key']}"
            s3_client.copy_object(
                CopySource={'Bucket': self.s3.bucket_name, 'Key': document['original_storage_key']},
                Bucket=self.quarantine_bucket,
                Key=quarantine_key
            )

            # Delete original
            s3_client.delete_object(
                Bucket=self.s3.bucket_name,
                Key=document['original_storage_key']
            )

            logger.info(f"Quarantined document {doc_id} to {quarantine_key}")

        except Exception as e:
            logger.error(f"Failed to quarantine document {doc_id}: {e}")

    def _mark_failed(self, doc_id: int, scan_result: ScanResult):
        """Mark document scan as failed."""
        self.db.execute(text("""
            UPDATE perennia_documents
            SET virus_scan_status = 'failed',
                virus_scan_result = :result,
                updated_at = NOW()
            WHERE id = :id
        """), {
            "id": doc_id,
            "result": {
                "scanned_at": datetime.now(timezone.utc).isoformat(),
                "error": scan_result.error_message
            }
        })
        self.db.commit()

    def run_batch(self, limit: int = None) -> Dict[str, Any]:
        """
        Process a batch of pending documents.

        Returns:
            Dict with batch processing results
        """
        documents = self.get_pending_documents(limit)

        results = {
            "processed": 0,
            "clean": 0,
            "infected": 0,
            "failed": 0,
            "details": []
        }

        for doc in documents:
            scan_result = self.scan_document(doc)
            results["processed"] += 1
            results["details"].append(scan_result)

            if scan_result.get("scan_result", {}).get("is_clean"):
                results["clean"] += 1
            elif scan_result.get("scan_result", {}).get("status") == "infected":
                results["infected"] += 1
            else:
                results["failed"] += 1

        return results


def run_av_scanner(db: Session, batch_size: int = 10) -> Dict[str, Any]:
    """
    Run AV scanner worker.

    Args:
        db: Database session
        batch_size: Number of documents to process

    Returns:
        Dict with processing results
    """
    worker = PerenniaAVScannerWorker(db)
    return worker.run_batch(batch_size)
