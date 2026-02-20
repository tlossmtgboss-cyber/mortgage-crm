#!/usr/bin/env python3
"""Rebase editor script to squash MUM fix commits into one."""
import sys

MUM_SHAS = {
    "34e12610",  # Fix MUM clients showing Salesforce IDs instead of borrower names
    "3d2e5e83",  # Fix MUM client import: rollback bug silently destroyed inserts
    "f3e2246a",  # Add fix-mum-client-names endpoint and improve name resolution
    "30dd990d",  # Fix SQL JOIN syntax in fix-mum-client-names
    "67393479",  # Detect Salesforce Contact IDs in borrower_name
    "18ded227",  # Add Salesforce Contact API resolution to fix-mum-client-names
    "86eeef3c",  # Add diagnostic output to fix-mum-client-names
    "819ed392",  # Fix SF Contact resolution: search any user's SF integration
    "ff01127f",  # Add detailed error reporting to SF Contact resolution step
    "0ddacc7e",  # Use integration_profiles + SalesforceOAuthService
    "e0f72bb9",  # Clean up diagnostic output from fix-mum-client-names
}

FIRST_MUM = "34e12610"  # oldest MUM commit - will be the "pick"

todo_file = sys.argv[1]

with open(todo_file, "r") as f:
    lines = f.readlines()

mum_lines = []
other_lines = []
first_mum_line = None

for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    # Extract sha from "pick <sha> <message>"
    parts = stripped.split(None, 2)
    if len(parts) < 2:
        other_lines.append(line)
        continue
    sha = parts[1][:8]
    if sha in MUM_SHAS:
        if sha == FIRST_MUM:
            first_mum_line = f"pick {parts[1]} {parts[2] if len(parts) > 2 else ''}\n"
        else:
            mum_lines.append(f"fixup {parts[1]} {parts[2] if len(parts) > 2 else ''}\n")
    else:
        other_lines.append(line)

# Build new todo: non-MUM commits in order, with MUM commits grouped at the
# position where the first MUM commit originally appeared
result = []
first_mum_inserted = False

# Re-read to maintain original ordering
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    parts = stripped.split(None, 2)
    if len(parts) < 2:
        result.append(line)
        continue
    sha = parts[1][:8]
    if sha in MUM_SHAS:
        if not first_mum_inserted:
            # Insert the first MUM pick + all fixups here
            result.append(first_mum_line)
            result.extend(mum_lines)
            first_mum_inserted = True
        # Skip individual MUM lines (already added above)
    else:
        result.append(line)

with open(todo_file, "w") as f:
    f.writelines(result)
