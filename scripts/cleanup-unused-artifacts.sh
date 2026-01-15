#!/bin/bash
# Cleanup script for unused Fabric artifacts
# Created: 2025-12-15
# Purpose: Remove unused/auto-generated Fabric artifacts to reduce clutter

echo "🧹 Cleaning up unused Fabric artifacts..."

# Define artifacts to remove
UNUSED_ARTIFACTS=(
    "fabric/StagingLakehouseForDataflows_20250822093021.SemanticModel"  # Auto-generated staging
    "fabric/StagingWarehouseForDataflows_20250822093045.SemanticModel"  # Auto-generated staging
    "fabric/oem_wh.SemanticModel"  # Empty warehouse semantic model (only 3 TMDL files)
    "fabric/oem_lh.SemanticModel"  # Auto-generated lakehouse semantic model (only 2 TMDL files)
    "fabric/copyjob1.CopyJob"  # Experimental/unused copy job
)

# Backup directory (in case we need to restore)
BACKUP_DIR=".archive/fabric-cleanup-$(date +%Y%m%d-%H%M%S)"

echo "📦 Creating backup at $BACKUP_DIR..."
mkdir -p "$BACKUP_DIR"

# Process each artifact
for artifact in "${UNUSED_ARTIFACTS[@]}"; do
    if [ -d "$artifact" ]; then
        echo "  Moving $artifact to backup..."
        mv "$artifact" "$BACKUP_DIR/" 2>/dev/null || echo "    ⚠️ Already removed or not found: $artifact"
    else
        echo "  ⏭️  Skipping (not found): $artifact"
    fi
done

echo ""
echo "✅ Cleanup complete! Removed artifacts backed up to: $BACKUP_DIR"
echo ""
echo "📊 Remaining semantic models:"
find fabric -type d -maxdepth 1 -name "*.SemanticModel" | grep -v "$BACKUP_DIR"
echo ""
echo "💡 To restore artifacts, run: mv $BACKUP_DIR/* fabric/"
echo "💡 To permanently delete backups, run: rm -rf $BACKUP_DIR"