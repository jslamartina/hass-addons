#!/bin/bash
set -e

echo "🚀 Setting up development environment..."

# Install Node.js
echo "📦 Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify installation
echo "✅ Node.js version: $(node --version)"
echo "✅ npm version: $(npm --version)"

# Initialize npm project
echo "📝 Initializing npm project..."
npm init -y

# Install Prettier and shell plugin
echo "🎨 Installing Prettier and shell plugin..."
npm install --save-dev prettier prettier-plugin-sh

# Create Prettier configuration
echo "⚙️ Creating Prettier configuration..."
cat > .prettierrc.json << 'EOF'
{
  "plugins": ["prettier-plugin-sh"]
}
EOF

# Create .prettierignore
echo "📋 Creating .prettierignore..."
cat > .prettierignore << 'EOF'
node_modules/
.git/
*.md

EOF

# Create format script
echo "📝 Creating format script..."
cat > .devcontainer/format.sh << 'EOF'
#!/bin/bash
set -e

echo "🎨 Formatting files with Prettier..."

# Format all files (including shell scripts)
npx prettier --write . --ignore-path .prettierignore

echo "✅ Formatting complete!"
EOF

chmod +x .devcontainer/format.sh

# Add npm scripts
echo "📦 Adding npm scripts..."
npm pkg set scripts.format="npx prettier --write ."
npm pkg set scripts.format:check="npx prettier --check ."
npm pkg set scripts.format:shell="npx prettier --write '**/*.sh'"
npm pkg set scripts.format:json="npx prettier --write '**/*.{json,yaml,yml}'"

echo "🎉 Setup complete! Prettier with shell plugin is ready to use."
echo "💡 Use 'npm run format' to format all files including shell scripts"
echo "💡 Use 'npm run format:shell' to format only shell scripts"
