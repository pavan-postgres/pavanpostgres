#!/bin/bash

# Step 1: Restart the pg_master container to apply changes
echo "Restarting pg_master container..."
docker-compose restart pg_master

# Wait for the container to be healthy again
echo "Waiting for pg_master to become healthy again..."
docker-compose exec pg_master bash -c "until pg_isready -U master_user -d testDB; do sleep 1; done"
