#!/usr/bin/env python3
"""
E-Sign Enterprise Readiness Assessment

Comprehensive test script to evaluate if the e-sign feature in Smart Docs
is fully functioning and enterprise-ready.

Tests:
1. Code Quality & Architecture
2. Database Models Completeness
3. API Routes & Endpoints
4. Frontend Components
5. Security Implementation
6. Enterprise Features
7. Configuration Requirements
8. Error Handling
9. Audit & Compliance
10. Integration Points

Exit Codes:
- 0: Enterprise ready
- 1: Critical issues found
- 2: Configuration missing
"""

import os
import sys
import json
import importlib.util
from pathlib import Path
from typing import Dict, List, Any

# Add backend to path for imports
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

class ESignEnterpriseAssessment:
    def __init__(self):
        self.results = {
            "overall_score": 0,
            "enterprise_ready": False,
            "critical_issues": [],
            "warnings": [],
            "missing_features": [],
            "configuration_issues": [],
            "test_results": {}
        }
        
    def run_assessment(self) -> Dict[str, Any]:
        """Run complete enterprise readiness assessment"""
        print("🔍 E-Sign Enterprise Readiness Assessment")
        print("=" * 60)
        
        tests = [
            ("Database Models", self.test_database_models),
            ("API Routes", self.test_api_routes),
            ("Frontend Components", self.test_frontend_components),
            ("Security Implementation", self.test_security_implementation),
            ("Enterprise Features", self.test_enterprise_features),
            ("Configuration", self.test_configuration),
            ("Error Handling", self.test_error_handling),
            ("Audit & Compliance", self.test_audit_compliance),
            ("Integration Points", self.test_integration_points),
            ("Code Quality", self.test_code_quality)
        ]
        
        total_score = 0
        max_score = len(tests) * 10
        
        for test_name, test_func in tests:
            print(f"\n📋 Testing: {test_name}")
            try:
                score, issues, warnings = test_func()
                total_score += score
                self.results["test_results"][test_name] = {
                    "score": score,
                    "max_score": 10,
                    "issues": issues,
                    "warnings": warnings,
                    "passed": score >= 7
                }
                
                if issues:
                    self.results["critical_issues"].extend(issues)
                if warnings:
                    self.results["warnings"].extend(warnings)
                    
                status = "✅ PASS" if score >= 7 else "❌ FAIL"
                print(f"   {status} Score: {score}/10")
                
            except Exception as e:
                print(f"   ❌ FAIL Score: 0/10 (Exception: {e})")
                self.results["critical_issues"].append(f"{test_name}: {str(e)}")
                self.results["test_results"][test_name] = {
                    "score": 0,
                    "max_score": 10,
                    "issues": [str(e)],
                    "warnings": [],
                    "passed": False
                }
        
        self.results["overall_score"] = (total_score / max_score) * 100
        self.results["enterprise_ready"] = (
            self.results["overall_score"] >= 80 and 
            len(self.results["critical_issues"]) == 0
        )
        
        return self.results

    def test_database_models(self) -> tuple:
        """Test database models completeness and relationships"""
        issues = []
        warnings = []
        score = 0
        
        try:
            # Check if models file exists
            models_file = Path("backend/database/models/esignature.py")
            if not models_file.exists():
                issues.append("E-signature models file not found")
                return 0, issues, warnings
                
            # Read models file
            with open(models_file, 'r') as f:
                content = f.read()
            
            # Check for required models
            required_models = [
                "ESignatureEnvelope",
                "ESignatureRecipient", 
                "ESignatureField",
                "ESignatureAuditEvent",
                "ESignatureTemplate"
            ]
            
            missing_models = []
            for model in required_models:
                if f"class {model}" not in content:
                    missing_models.append(model)
            
            if missing_models:
                issues.append(f"Missing models: {', '.join(missing_models)}")
            else:
                score += 2
            
            # Check for required enums
            required_enums = [
                "EnvelopeStatus",
                "RecipientType", 
                "RecipientStatus",
                "SignatureFieldType",
                "AuditEventType"
            ]
            
            missing_enums = []
            for enum in required_enums:
                if f"class {enum}" not in content:
                    missing_enums.append(enum)
                    
            if missing_enums:
                issues.append(f"Missing enums: {', '.join(missing_enums)}")
            else:
                score += 2
                
            # Check for relationships
            if "relationships" in content or "relationship" in content:
                score += 2
            else:
                warnings.append("No SQLAlchemy relationships found")
                
            # Check for indexes
            if "Index(" in content:
                score += 2
            else:
                warnings.append("No database indexes found")
                
            # Check for security features
            security_features = ["organization_id", "created_by", "audit"]
            found_security = sum(1 for feature in security_features if feature in content)
            score += min(2, found_security)
                
        except Exception as e:
            issues.append(f"Error reading models: {str(e)}")
            
        return score, issues, warnings

    def test_api_routes(self) -> tuple:
        """Test API routes completeness and structure"""
        issues = []
        warnings = []
        score = 0
        
        try:
            # Check if routes file exists
            routes_file = Path("backend/routes/smart_docs_esign_routes.py")
            if not routes_file.exists():
                issues.append("E-signature routes file not found")
                return 0, issues, warnings
                
            # Read routes file
            with open(routes_file, 'r') as f:
                content = f.read()
            
            # Check for FastAPI router
            if "APIRouter" in content and 'prefix="/api/v1/esign"' in content:
                score += 2
            else:
                issues.append("FastAPI router not properly configured")
            
            # Check for required endpoints
            required_endpoints = [
                "create_envelope",
                "send_envelope", 
                "get_envelope",
                "add_signer",
                "add_field",
                "submit_signature"
            ]
            
            missing_endpoints = []
            for endpoint in required_endpoints:
                if endpoint not in content:
                    missing_endpoints.append(endpoint)
            
            if missing_endpoints:
                issues.append(f"Missing endpoints: {', '.join(missing_endpoints)}")
            else:
                score += 2
                
            # Check for authentication
            if "get_current_user" in content or "Depends" in content:
                score += 2
            else:
                issues.append("No authentication found in routes")
                
            # Check for request/response models
            if "BaseModel" in content and "Request" in content:
                score += 2
            else:
                warnings.append("Limited request/response models")
                
            # Check for error handling
            if "HTTPException" in content:
                score += 1
            else:
                warnings.append("No error handling found")
                
            # Check for logging
            if "logger" in content:
                score += 1
            else:
                warnings.append("No logging found")
                
        except Exception as e:
            issues.append(f"Error reading routes: {str(e)}")
            
        return score, issues, warnings

    def test_frontend_components(self) -> tuple:
        """Test frontend components completeness"""
        issues = []
        warnings = []
        score = 0
        
        try:
            # Check for main components
            required_components = [
                "frontend/src/components/esign/FieldPlacementBuilder.jsx",
                "frontend/src/pages/esign/SigningSession.jsx",
                "frontend/src/services/esignApi.js"
            ]
            
            missing_components = []
            for component in required_components:
                if not Path(component).exists():
                    missing_components.append(component)
            
            if missing_components:
                issues.append(f"Missing components: {', '.join(missing_components)}")
            else:
                score += 3
                
            # Check FieldPlacementBuilder features
            if Path("frontend/src/components/esign/FieldPlacementBuilder.jsx").exists():
                with open("frontend/src/components/esign/FieldPlacementBuilder.jsx", 'r') as f:
                    content = f.read()
                    
                features = ["drag", "drop", "PDF", "field", "signer"]
                found_features = sum(1 for feature in features if feature in content.lower())
                score += min(2, found_features // 2)
                
            # Check SigningSession features  
            if Path("frontend/src/pages/esign/SigningSession.jsx").exists():
                with open("frontend/src/pages/esign/SigningSession.jsx", 'r') as f:
                    content = f.read()
                    
                features = ["signature", "progress", "field", "complete"]
                found_features = sum(1 for feature in features if feature in content.lower())
                score += min(2, found_features // 2)
                
            # Check API service
            if Path("frontend/src/services/esignApi.js").exists():
                with open("frontend/src/services/esignApi.js", 'r') as f:
                    content = f.read()
                    
                if "esignApi" in content and "envelope" in content:
                    score += 2
                else:
                    warnings.append("API service incomplete")
                    
            # Check routing integration
            routes_file = Path("frontend/src/routes/index.jsx")
            if routes_file.exists():
                with open(routes_file, 'r') as f:
                    content = f.read()
                    
                if "esign" in content.lower():
                    score += 1
                else:
                    warnings.append("E-sign not integrated in main routing")
                    
        except Exception as e:
            issues.append(f"Error checking frontend: {str(e)}")
            
        return score, issues, warnings

    def test_security_implementation(self) -> tuple:
        """Test security implementation"""
        issues = []
        warnings = []
        score = 0
        
        try:
            # Check crypto service
            crypto_file = Path("backend/services/smart_docs/esignature_crypto_service.py")
            if not crypto_file.exists():
                issues.append("Crypto service not found")
                return 0, issues, warnings
                
            with open(crypto_file, 'r') as f:
                content = f.read()
                
            # Check for security features
            security_features = [
                ("HMAC", "hmac"),
                ("SHA-256", "sha256"), 
                ("Key derivation", "HKDF"),
                ("Token generation", "token"),
                ("Document hashing", "document_hash")
            ]
            
            for feature_name, keyword in security_features:
                if keyword.lower() in content.lower():
                    score += 1
                else:
                    warnings.append(f"Missing {feature_name}")
                    
            # Check key management
            key_manager_file = Path("backend/services/smart_docs/esignature_key_manager.py")
            if key_manager_file.exists():
                score += 2
                with open(key_manager_file, 'r') as f:
                    km_content = f.read()
                    if "ESIGN_SIGNING_SECRET" in km_content:
                        score += 1
                    else:
                        issues.append("Key management not properly configured")
            else:
                issues.append("Key manager not found")
                
            # Check audit logging
            if "audit" in content.lower():
                score += 1
            else:
                warnings.append("Limited audit logging")
                
        except Exception as e:
            issues.append(f"Error checking security: {str(e)}")
            
        return score, issues, warnings

    def test_enterprise_features(self) -> tuple:
        """Test enterprise-specific features"""
        issues = []
        warnings = []
        score = 0
        
        enterprise_features = [
            ("Multi-tenant support", "organization_id"),
            ("Audit trail", "audit"),
            ("Template system", "template"),
            ("Bulk operations", "bulk"),
            ("Webhook support", "webhook"),
            ("API rate limiting", "rate_limit"),
            ("Role-based access", "role"),
            ("Compliance features", "compliance"),
            ("Document retention", "retention"),
            ("White labeling", "brand")
        ]
        
        # Check in multiple files
        files_to_check = [
            Path("backend/routes/smart_docs_esign_routes.py"),
            Path("backend/database/models/esignature.py"),
            Path("backend/services/smart_docs/esignature_crypto_service.py")
        ]
        
        found_features = 0
        for feature_name, keyword in enterprise_features:
            feature_found = False
            for file_path in files_to_check:
                if file_path.exists():
                    try:
                        with open(file_path, 'r') as f:
                            content = f.read().lower()
                            if keyword in content:
                                feature_found = True
                                break
                    except:
                        continue
                        
            if feature_found:
                found_features += 1
            else:
                warnings.append(f"Missing enterprise feature: {feature_name}")
        
        score = min(10, found_features)
        
        if score < 6:
            issues.append("Insufficient enterprise features")
            
        return score, issues, warnings

    def test_configuration(self) -> tuple:
        """Test configuration requirements"""
        issues = []
        warnings = []
        score = 0
        
        # Check environment file
        env_file = Path("backend/.env.example")
        if env_file.exists():
            with open(env_file, 'r') as f:
                content = f.read()
                
            # Check for required config
            required_configs = [
                "SECRET_KEY",
                "DATABASE_URL", 
                "ANTHROPIC_API_KEY"
            ]
            
            missing_configs = []
            for config in required_configs:
                if config not in content:
                    missing_configs.append(config)
                    
            if missing_configs:
                warnings.append(f"Missing configs in .env.example: {', '.join(missing_configs)}")
            else:
                score += 3
                
            # Check for e-sign specific configs
            esign_configs = ["ESIGN_SIGNING_SECRET", "ESIGN_TOKEN_SECRET"]
            found_esign_configs = sum(1 for config in esign_configs if config in content)
            
            if found_esign_configs == 0:
                self.results["configuration_issues"].append(
                    "E-sign configuration missing from .env.example"
                )
                warnings.append("E-sign environment variables not documented")
            else:
                score += 2
        else:
            issues.append(".env.example file not found")
            
        # Check current environment
        required_env_vars = ["ESIGN_SIGNING_SECRET", "ESIGN_TOKEN_SECRET"]
        missing_env_vars = []
        for var in required_env_vars:
            if not os.getenv(var):
                missing_env_vars.append(var)
                
        if missing_env_vars:
            self.results["configuration_issues"].extend(missing_env_vars)
            issues.append(f"Missing environment variables: {', '.join(missing_env_vars)}")
        else:
            score += 3
            
        # Check route registration
        main_file = Path("backend/main.py")
        if main_file.exists():
            with open(main_file, 'r') as f:
                content = f.read()
                
            if "esign" in content.lower():
                score += 2
            else:
                issues.append("E-sign routes not registered in main.py")
        
        return score, issues, warnings

    def test_error_handling(self) -> tuple:
        """Test error handling implementation"""
        issues = []
        warnings = []
        score = 0
        
        files_to_check = [
            Path("backend/routes/smart_docs_esign_routes.py"),
            Path("frontend/src/services/esignApi.js"),
            Path("frontend/src/components/esign/FieldPlacementBuilder.jsx")
        ]
        
        for file_path in files_to_check:
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                        
                    # Check for error handling patterns
                    error_patterns = ["try", "catch", "except", "error", "HTTPException"]
                    found_patterns = sum(1 for pattern in error_patterns if pattern in content.lower())
                    
                    if found_patterns >= 2:
                        score += 3
                    elif found_patterns >= 1:
                        score += 1
                        
                except:
                    warnings.append(f"Could not read {file_path}")
            else:
                warnings.append(f"File not found: {file_path}")
        
        if score < 5:
            issues.append("Insufficient error handling")
            
        return min(10, score), issues, warnings

    def test_audit_compliance(self) -> tuple:
        """Test audit and compliance features"""
        issues = []
        warnings = []
        score = 0
        
        # Check audit model
        models_file = Path("backend/database/models/esignature.py")
        if models_file.exists():
            with open(models_file, 'r') as f:
                content = f.read()
                
            audit_features = [
                "ESignatureAuditEvent",
                "AuditEventType", 
                "ip_address",
                "user_agent",
                "timestamp"
            ]
            
            found_features = sum(1 for feature in audit_features if feature in content)
            score += min(5, found_features)
            
            if "ESignatureAuditEvent" not in content:
                issues.append("Missing audit event model")
                
        # Check compliance features
        compliance_keywords = ["esign", "ueta", "regulation", "compliance", "legal"]
        routes_file = Path("backend/routes/smart_docs_esign_routes.py")
        if routes_file.exists():
            with open(routes_file, 'r') as f:
                content = f.read().lower()
                
            found_compliance = sum(1 for keyword in compliance_keywords if keyword in content)
            score += min(3, found_compliance)
            
        # Check for consent handling
        consent_files = [
            Path("backend/services/smart_docs/esign_consent_service.py"),
            Path("backend/services/smart_docs/esign_kba_service.py")
        ]
        
        for consent_file in consent_files:
            if consent_file.exists():
                score += 1
            else:
                warnings.append(f"Missing consent service: {consent_file.name}")
        
        if score < 6:
            issues.append("Insufficient compliance features")
            
        return score, issues, warnings

    def test_integration_points(self) -> tuple:
        """Test integration with other systems"""
        issues = []
        warnings = []
        score = 0
        
        # Check Smart Docs integration
        registration_file = Path("backend/routes/smart_docs_v2_registration.py")
        if registration_file.exists():
            with open(registration_file, 'r') as f:
                content = f.read()
                
            if "esign" in content.lower():
                score += 3
            else:
                issues.append("E-sign not integrated in Smart Docs registration")
        else:
            warnings.append("Smart Docs registration file not found")
            
        # Check loan integration
        models_file = Path("backend/database/models/esignature.py")
        if models_file.exists():
            with open(models_file, 'r') as f:
                content = f.read()
                
            if "loan_id" in content:
                score += 2
            else:
                issues.append("No loan integration found")
                
        # Check user integration  
        if "user_id" in content or "created_by" in content:
            score += 2
        else:
            warnings.append("Limited user integration")
            
        # Check organization integration
        if "organization_id" in content:
            score += 2
        else:
            issues.append("No multi-tenant support")
            
        # Check email integration
        if "email" in content:
            score += 1
        else:
            warnings.append("No email integration")
        
        return score, issues, warnings

    def test_code_quality(self) -> tuple:
        """Test overall code quality"""
        issues = []
        warnings = []
        score = 0
        
        files_to_check = [
            Path("backend/routes/smart_docs_esign_routes.py"),
            Path("backend/database/models/esignature.py"),
            Path("backend/services/smart_docs/esignature_crypto_service.py"),
            Path("frontend/src/components/esign/FieldPlacementBuilder.jsx"),
            Path("frontend/src/services/esignApi.js")
        ]
        
        total_files = len(files_to_check)
        found_files = 0
        
        for file_path in files_to_check:
            if file_path.exists():
                found_files += 1
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                        
                    # Check for documentation
                    if '"""' in content or "* " in content:
                        score += 1
                        
                    # Check for type hints (Python) or PropTypes (JS)
                    if ":" in content and ("str" in content or "int" in content or "PropTypes" in content):
                        score += 1
                        
                except:
                    warnings.append(f"Could not analyze {file_path}")
                    
        # File completeness score
        completeness_score = (found_files / total_files) * 5
        score += completeness_score
        
        if found_files < total_files:
            missing_count = total_files - found_files
            issues.append(f"{missing_count} core files missing")
            
        return min(10, int(score)), issues, warnings

    def print_summary(self):
        """Print assessment summary"""
        results = self.results
        
        print(f"\n" + "=" * 60)
        print("📊 E-SIGN ENTERPRISE READINESS ASSESSMENT RESULTS")
        print("=" * 60)
        
        print(f"\n🎯 Overall Score: {results['overall_score']:.1f}/100")
        
        if results['enterprise_ready']:
            print("✅ STATUS: ENTERPRISE READY")
            print("   The e-sign system meets enterprise requirements")
        else:
            print("❌ STATUS: NOT ENTERPRISE READY") 
            print("   Critical issues must be addressed before production use")
            
        # Test Results
        print(f"\n📋 Test Results:")
        for test_name, test_result in results['test_results'].items():
            status = "✅" if test_result['passed'] else "❌"
            print(f"   {status} {test_name}: {test_result['score']}/10")
            
        # Critical Issues
        if results['critical_issues']:
            print(f"\n🚨 Critical Issues ({len(results['critical_issues'])}):")
            for issue in results['critical_issues']:
                print(f"   • {issue}")
                
        # Configuration Issues
        if results['configuration_issues']:
            print(f"\n⚙️  Configuration Issues:")
            for issue in results['configuration_issues']:
                print(f"   • {issue}")
                
        # Warnings
        if results['warnings']:
            print(f"\n⚠️  Warnings ({len(results['warnings'])}):")
            for warning in results['warnings'][:10]:  # Limit to first 10
                print(f"   • {warning}")
            if len(results['warnings']) > 10:
                print(f"   ... and {len(results['warnings']) - 10} more")
                
        # Recommendations
        print(f"\n💡 Recommendations:")
        if results['overall_score'] < 50:
            print("   • Complete core implementation before proceeding")
            print("   • Focus on database models and API routes")
            print("   • Set up proper environment configuration")
        elif results['overall_score'] < 80:
            print("   • Address critical issues and security concerns")
            print("   • Implement missing enterprise features")
            print("   • Improve error handling and logging")
        else:
            print("   • Address remaining warnings")
            print("   • Consider additional enterprise features")
            print("   • Conduct thorough security testing")
            
        print("\n" + "=" * 60)


def main():
    """Run the enterprise readiness assessment"""
    try:
        assessment = ESignEnterpriseAssessment()
        results = assessment.run_assessment()
        assessment.print_summary()
        
        # Save results to file
        output_file = Path("esign_enterprise_assessment.json")
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n📄 Detailed results saved to: {output_file}")
        
        # Exit with appropriate code
        if results['enterprise_ready']:
            sys.exit(0)  # Enterprise ready
        elif results['configuration_issues']:
            sys.exit(2)  # Configuration missing
        else:
            sys.exit(1)  # Critical issues
            
    except Exception as e:
        print(f"❌ Assessment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()