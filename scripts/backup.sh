#!/bin/bash

# ===========================================
# CoinBourg Backup Script
# ===========================================
# Creates backups of database and configuration

set -e

BACKUP_DIR="/home/${USER}/coinbourg/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="coinbourg_backup_${DATE}"

# Create backup directory
mkdir -p ${BACKUP_DIR}

echo "Creating backup: ${BACKUP_NAME}"

# Backup PostgreSQL database
echo "Backing up database..."
docker exec coinbourg-db pg_dump -U coinbourg coinbourg > "${BACKUP_DIR}/${BACKUP_NAME}_db.sql"

# Backup configuration
echo "Backing up configuration..."
cp .env "${BACKUP_DIR}/${BACKUP_NAME}_env.bak"

# Compress backup
echo "Compressing backup..."
tar -czvf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" \
    -C "${BACKUP_DIR}" \
    "${BACKUP_NAME}_db.sql" \
    "${BACKUP_NAME}_env.bak"

# Clean up individual files
rm "${BACKUP_DIR}/${BACKUP_NAME}_db.sql"
rm "${BACKUP_DIR}/${BACKUP_NAME}_env.bak"

# Remove backups older than 7 days
find ${BACKUP_DIR} -name "coinbourg_backup_*.tar.gz" -mtime +7 -delete

echo "Backup complete: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
