# Backstage GitHub Automation

This tool automates the process of integrating repositories with Backstage, including:
- Creating catalog-info.yaml files
- Opening PRs and issues
- Publishing to Backstage
- Setting up GitHub App integration
- Support for GitHub Enterprise servers

## Requirements

- Python 3.8+
- GitHub Personal Access Token
- Access to a Backstage instance
- Organization admin permissions
- (Optional) GitHub Enterprise API URL

## Installation

1. Clone this repository
2. Install dependencies:
```bash
python -m pip install -r requirements.txt
```

## Usage

### Using the Web Interface

1. Start the Streamlit app:
```bash
streamlit run app.py
```

2. Open your browser and navigate to the URL shown in the terminal (usually http://localhost:8501)

3. In the sidebar:
   - Enter your GitHub token
   - Enter your organization name
   - Enter your Backstage URL
   - (Optional) Enter your GitHub API URL for enterprise servers
   - Click "Save Configuration"

4. Use the dashboard to:
   - View the status of all repositories
   - Select and onboard new repositories
   - Monitor onboarding progress

### Using the Command Line

Set the required environment variables:

```bash
export GITHUB_TOKEN="your-github-token"
export GITHUB_ORG="your-org-name"
export BACKSTAGE_URL="https://your-backstage-instance"
# Optional: For GitHub Enterprise
export GITHUB_API_URL="https://github.enterprise.com/api/v3"
```

Run the automation script:

```bash
python backstage_automation.py
```

## Environment Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Fill in your environment variables in `.env`:
   - Required variables:
     - `GITHUB_TOKEN`: Your GitHub Personal Access Token
     - `GITHUB_ORG`: Your GitHub organization name
     - `BACKSTAGE_URL`: Your Backstage instance URL
     - `BACKSTAGE_TOKEN`: Your Backstage API token for authentication
     - `BACKSTAGE_ENCRYPTION_KEY`: Generated encryption key
   - Optional variables:
     - `GITHUB_API_URL`: GitHub Enterprise API URL
     - `DEFAULT_ORG`: Default organization for automation
     - `CHECK_ONLY`: Set to "true" for dry-run mode

⚠️ Important:
- Never commit `.env` file to version control
- Keep your encryption key secure
- Don't include local machine paths in configurations
- Use relative paths in scripts and configurations

## Features

1. **Web Interface**:
   - Dashboard showing repository status
   - Bulk repository onboarding
   - Real-time status updates
   - GitHub Enterprise support

2. **Automation**:
   - Catalog file creation
   - PR and Issue management
   - Backstage integration
   - GitHub App setup

## GitHub Workflows

This project includes several GitHub Actions workflows that work together to automate Backstage integration. Here's how to set them up and use them:

### Required Secrets

Set these secrets in your GitHub organization or repository settings:

1. `AUTOMATION_TOKEN`: GitHub Personal Access Token with:
   - `repo` scope for repository access
   - `workflow` scope for workflow triggers
   - `admin:org` scope for organization management

2. `BACKSTAGE_URL`: Your Backstage instance URL
   - Format: `https://your-backstage-instance`
   - Must be accessible from GitHub Actions

3. `BACKSTAGE_TOKEN`: Backstage API token
   - Required for authentication with Backstage API
   - Generate from your Backstage instance
   - Must have permissions to register catalog entities
   - Token type can be configured with BACKSTAGE_TOKEN_TYPE (defaults to "Bearer")

4. `BACKSTAGE_ENCRYPTION_KEY`: Encryption key for secure storage
   - Generate using: 
     ```bash
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
   - Must be set at organization level for consistent encryption across repositories
   - Same key must be used across all automation workflows
   - ⚠️ Keep this key secure and never commit it to version control

4. `GITHUB_API_URL` (Optional):
   - Only required for GitHub Enterprise
   - Format: `https://github.enterprise.com/api/v3`

#### Setting Up Secrets in GitHub:

1. Organization-wide secrets (Recommended):
   ```bash
   # First, generate your encryption key
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   
   Then:
   1. Go to your GitHub organization settings
   2. Navigate to Security → Secrets and variables → Actions
   3. Click "New organization secret"
   4. Add each secret:
      - Name: `BACKSTAGE_ENCRYPTION_KEY`
      - Value: (the generated key)
      - Select repositories that can access this secret
   5. Repeat for `AUTOMATION_TOKEN`, `BACKSTAGE_URL`, and optionally `GITHUB_API_URL`

2. Repository-level secrets (Alternative):
   ```bash
   # For each repository:
   gh secret set BACKSTAGE_ENCRYPTION_KEY --body "your-generated-key"
   gh secret set AUTOMATION_TOKEN --body "your-github-token"
   gh secret set BACKSTAGE_URL --body "https://your-backstage-instance"
   ```

⚠️ Important Notes:
- Use the same `BACKSTAGE_ENCRYPTION_KEY` across all repositories using this automation
- Rotate secrets periodically (especially `AUTOMATION_TOKEN`)
- When rotating `BACKSTAGE_ENCRYPTION_KEY`, re-encrypt all stored configurations
- Store backup of `BACKSTAGE_ENCRYPTION_KEY` in a secure password manager

### Available Workflows

1. **publish-backstage-reusable.yml**
   - Purpose: Core workflow for publishing catalog entries to Backstage
   - Triggers: Called by other workflows
   - Parameters:
     - `repository`: Name of the repository to process
   - Secrets used: All of the above
   - Features:
     - Direct API integration with Backstage
     - Handles both Component and API registrations
     - Validates YAML before publishing

2. **publish-backstage.yml**
   - Purpose: Main entry point for publishing
   - Triggers:
     - When PRs with catalog-info.yaml changes are merged
     - Manual workflow dispatch
   - Parameters:
     - `repository`: (Optional) Repository name for manual triggers
   - Uses: Calls the reusable workflow

3. **backstage-automation.yml**
   - Purpose: Main automation workflow for repository onboarding
   - Triggers:
     - Daily at midnight (requires successful canary run)
     - Manual workflow dispatch with inputs
   - Parameters:
     - `organization`: GitHub Organization Name
     - `backstage_url`: Backstage Instance URL
     - `github_api_url`: (Optional) GitHub Enterprise API URL
     - `canary_repo`: (Optional) Single repository for canary testing
   - Features:
     - Canary testing mode for safe deployments
     - Scans all repositories in organization
     - Creates catalog-info.yaml files
     - Opens PRs for Backstage integration
     - Handles API and Component registration
   - Canary Mode:
     - Test changes on a single repository
     - Automated status tracking
     - Scheduled runs require successful canary
   
4. **check-status.yml**
   - Purpose: Monitor onboarding progress and status
   - Triggers:
     - Every 4 hours
     - Manual workflow dispatch
   - Parameters:
     - `organization`: (Optional) GitHub Organization Name
   - Features:
     - Generates status reports for all repositories
     - Creates GitHub workflow summary
     - Tracks onboarding progress
     - Identifies failed integrations

5. **handle-force-merge.yml**
   - Purpose: Safely handle force merge requests
   - Triggers: On issue comment containing `/force-merge`
   - Features:
     - Validates merge request authorization
     - Temporarily disables branch protection
     - Performs squash merge of integration PR
     - Restores branch protection settings
     - Updates issue with merge status
   - Security:
     - Requires proper permissions
     - Logs all force merge actions
     - Maintains audit trail

6. **analyze-backstage-candidates.yml**
   - Purpose: Identifies repositories ready for Backstage
   - Triggers:
     - Weekly on Monday at midnight
     - Manual workflow dispatch
   - Features:
     - Scores repositories based on multiple criteria
     - Generates prioritization report
     - Creates GitHub issues with findings

### Organization Setup Steps

1. Repository Setup:
   ```bash
   # Clone the automation repository
   git clone https://github.com/your-org/backstage-github.git
   cd backstage-github
   
   # Install dependencies
   python -m pip install -r requirements.txt
   ```

2. Configure Organization Secrets:
   - Go to your GitHub organization settings
   - Navigate to Security > Secrets and variables > Actions
   - Add the required secrets (AUTOMATION_TOKEN, BACKSTAGE_URL)

3. Enable Workflows:
   ```bash
   # Enable required workflows
   gh workflow enable publish-backstage-reusable.yml
   gh workflow enable publish-backstage.yml
   gh workflow enable backstage-automation.yml
   gh workflow enable check-status.yml
   gh workflow enable handle-force-merge.yml
   gh workflow enable analyze-backstage-candidates.yml
   ```

4. Initial Analysis:
   - Run the analysis workflow to identify candidates:
   ```bash
   gh workflow run analyze-backstage-candidates.yml -f organization=your-org-name
   ```

5. Monitor Progress:
   - Check the Actions tab for workflow runs
   - Review generated reports and issues
   - Track onboarding progress through the Streamlit dashboard

### Canary Testing Mode

The automation workflow supports a canary testing mode to safely validate changes before applying them across the organization.

#### How It Works

1. **Canary Mode Execution**:
   ```bash
   # Run workflow with canary repository
   gh workflow run backstage-automation.yml \
     -f organization="your-org-name" \
     -f backstage_url="your-backstage-url" \
     -f canary_repo="test-repository"
   ```

2. **Status Tracking**:
   - Successful canary runs are recorded in `.github/canary-status.json`
   - Contains timestamp and repository name of last successful run
   - Automatically updated by the workflow

3. **Scheduled Run Protection**:
   - Daily scheduled runs check canary status first
   - Only proceed if a successful canary run exists
   - Prevents mass changes without validation
   - Manual runs are not affected by canary status

4. **Best Practice Workflow**:
   1. Test changes with canary repository first
   2. Monitor the canary run results
   3. Once successful, scheduled runs will automatically resume
   4. Reset canary status if needed by:
      - Deleting `.github/canary-status.json`
      - Setting status values to `null`
      - Running a new canary test

5. **Canary Selection Tips**:
   - Choose a representative repository
   - Include typical features (API specs, docs)
   - Ensure proper permissions exist
   - Test with both simple and complex cases

### Best Practices

1. **Repository Selection**:
   - Start with actively maintained repositories
   - Prioritize repositories with good documentation
   - Focus on services and APIs first
   - Use canary testing for initial validation

2. **Workflow Management**:
   - Monitor workflow runs regularly
   - Set up notifications for failures
   - Review and update workflow permissions as needed

3. **Security**:
   - Rotate AUTOMATION_TOKEN regularly
   - Review workflow logs for sensitive information
   - Maintain least-privilege access principles

## Error Handling

The script includes comprehensive error handling and will:
- Validate all required credentials
- Check for required permissions
- Handle API rate limiting
- Provide clear error messages

## Security Key Management

The application uses encryption for storing sensitive configuration data. To set this up:

1. Generate an encryption key (this will happen automatically on first run), or run:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Set the encryption key in your environment:
   ```bash
   # For local development
   export BACKSTAGE_ENCRYPTION_KEY="your-generated-key"
   
   # For production/CI environments, set this as a secure environment variable
   ```

3. For GitHub Actions, add BACKSTAGE_ENCRYPTION_KEY as a secret:
   - Go to repository/organization settings
   - Navigate to Secrets and Variables > Actions
   - Add BACKSTAGE_ENCRYPTION_KEY with your generated key

⚠️ IMPORTANT SECURITY NOTES:
- Never commit the encryption key to version control
- Rotate the encryption key periodically
- Back up your encryption key securely
- When rotating keys, re-encrypt existing data with the new key

## Contributing

Feel free to open issues or submit pull requests for improvements.
