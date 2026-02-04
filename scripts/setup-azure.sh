#!/bin/bash
# Azure Container Apps Infrastructure Setup Script
# Run this script to create the Azure resources needed for deployment

set -e

# Configuration - Modify these values
RESOURCE_GROUP="rg-genai-student-jp"
LOCATION="japaneast"  # Choose: japaneast, eastus, westeurope, etc.
CONTAINER_APP_ENV="rag-env"
CONTAINER_APP_NAME="serverless-rag-api"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Azure Container Apps Setup ===${NC}"
echo ""

# Check if logged in
echo "Checking Azure CLI login status..."
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Not logged in. Running 'az login'...${NC}"
    az login
fi

SUBSCRIPTION=$(az account show --query name -o tsv)
echo -e "Using subscription: ${GREEN}$SUBSCRIPTION${NC}"
echo ""

# Create Resource Group
echo "Creating Resource Group: $RESOURCE_GROUP..."
az group create \
    --name $RESOURCE_GROUP \
    --location $LOCATION \
    --output none
echo -e "${GREEN}✓ Resource Group created${NC}"

# Create Container Apps Environment
echo "Creating Container Apps Environment: $CONTAINER_APP_ENV..."
az containerapp env create \
    --name $CONTAINER_APP_ENV \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION \
    --output none
echo -e "${GREEN}✓ Container Apps Environment created${NC}"

# Create Container App (placeholder image, will be updated by CD)
echo "Creating Container App: $CONTAINER_APP_NAME..."
az containerapp create \
    --name $CONTAINER_APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --environment $CONTAINER_APP_ENV \
    --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
    --target-port 8000 \
    --ingress external \
    --min-replicas 0 \
    --max-replicas 1 \
    --cpu 0.5 \
    --memory 1Gi \
    --output none

# Get the app URL
APP_URL=$(az containerapp show \
    --name $CONTAINER_APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --query properties.configuration.ingress.fqdn \
    -o tsv)

echo -e "${GREEN}✓ Container App created${NC}"
echo ""

# Create Service Principal for GitHub Actions
echo "Creating Service Principal for GitHub Actions..."
SP_OUTPUT=$(az ad sp create-for-rbac \
    --name "sp-github-rag-deploy" \
    --role contributor \
    --scopes /subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP \
    --sdk-auth)

echo ""
echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo ""
echo -e "Container App URL: ${GREEN}https://$APP_URL${NC}"
echo ""
echo -e "${YELLOW}=== IMPORTANT: GitHub Secrets Setup ===${NC}"
echo ""
echo "Add this as a GitHub secret named 'AZURE_CREDENTIALS':"
echo ""
echo -e "${GREEN}$SP_OUTPUT${NC}"
echo ""
echo "Also add these secrets for the app environment:"
echo "  - AZURE_SEARCH_ENDPOINT"
echo "  - AZURE_SEARCH_API_KEY"  
echo "  - AZURE_SEARCH_INDEX_NAME"
echo ""
echo -e "${YELLOW}To update the Container App with environment variables, run:${NC}"
echo "az containerapp update \\"
echo "  --name $CONTAINER_APP_NAME \\"
echo "  --resource-group $RESOURCE_GROUP \\"
echo "  --set-env-vars \\"
echo "    AZURE_SEARCH_ENDPOINT=<your-endpoint> \\"
echo "    AZURE_SEARCH_API_KEY=<your-key> \\"
echo "    AZURE_SEARCH_INDEX_NAME=<your-index>"
