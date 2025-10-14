#!/bin/bash
set -e

echo "🎭 Setting up Playwright..."

# Install Playwright browsers
echo "📦 Installing Playwright browsers (Chromium)..."
npx playwright install chromium --with-deps

# Install system dependencies for Playwright
echo "🔧 Installing Playwright system dependencies..."
npx playwright install-deps chromium

# Add npm scripts for Playwright if they don't exist
echo "📝 Adding Playwright npm scripts..."
npm pkg set scripts.playwright:install="npx playwright install chromium --with-deps"
npm pkg set scripts.playwright:delete-entities="ts-node scripts/playwright/delete-entities.ts"
npm pkg set scripts.playwright:test="npx playwright test"

echo "✅ Playwright setup complete!"
echo "💡 Use 'npm run playwright:delete-entities <entity1> <entity2>' to delete entities"
echo "💡 Use 'npm run playwright:install' to reinstall browsers if needed"
