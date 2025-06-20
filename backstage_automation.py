import os
import time
from github import Github
import yaml
import requests
from typing import Tuple, Dict, Any, List
from datetime import datetime

class BackstageAutomation:
    def __init__(self, github_token: str, org_name: str, github_api_url: str = None):
        """Initialize the BackstageAutomation class.

        Args:
            github_token (str): GitHub personal access token
            org_name (str): GitHub organization name
            github_api_url (str, optional): Custom GitHub API URL for enterprise servers
        """
        if github_api_url:
            self.github = Github(base_url=github_api_url, login_or_token=github_token)
        else:
            self.github = Github(github_token)
        self.org = self.github.get_organization(org_name)
        self.base_branch = "main"
        self.github_api_url = github_api_url
        self.status_report = []

    def _determine_component_type(self, repo: Any) -> str:
        """Determine the component type based on repository content.

        Args:
            repo: GitHub repository object

        Returns:
            str: Component type (library, service, website, etc.)
        """
        try:
            # Check for common service indicators
            if any(repo.get_contents(file) for file in ["Dockerfile", "docker-compose.yml", "k8s", "kubernetes"]):
                return "service"
            # Check for website/frontend indicators
            elif any(repo.get_contents(file) for file in ["package.json", "index.html", "public/index.html", "src/index.js"]):
                return "website"
            # Check for library indicators
            elif any(repo.get_contents(file) for file in ["setup.py", "composer.json", "go.mod"]):
                return "library"
            # Default to service if unclear
            return "service"
        except Exception:
            return "service"

    def _determine_lifecycle(self, repo: Any) -> str:
        """Determine the lifecycle stage based on repository metadata.

        Args:
            repo: GitHub repository object

        Returns:
            str: Lifecycle stage
        """
        try:
            # Check if repository is archived
            if repo.archived:
                return "deprecated"
            
            # Check for production indicators in branch protection
            if repo.get_branch(self.base_branch).get_protection():
                return "production"
            
            # Check repository age and activity
            created_date = repo.created_at
            last_push = repo.pushed_at
            commits = repo.get_commits()
            
            if (datetime.now() - created_date).days < 90:  # Less than 3 months old
                return "experimental"
            elif commits.totalCount > 100 and last_push:  # Active with significant history
                return "production"
            else:
                return "development"
        except Exception:
            return "production"

    def _determine_owner(self, repo: Any) -> str:
        """Determine the component owner based on repository metadata.

        Args:
            repo: GitHub repository object

        Returns:
            str: Owner (team or individual)
        """
        try:
            # Try to get CODEOWNERS file
            try:
                codeowners = repo.get_contents("CODEOWNERS")
                if codeowners:
                    content = codeowners.decoded_content.decode()
                    # Look for team mentions in CODEOWNERS
                    import re
                    teams = re.findall(r'@[\w-]+/[\w-]+', content)
                    if teams:
                        return teams[0].replace('@', '')  # Return first team found
            except Exception:
                pass

            # Try to get most active contributors
            contributors = repo.get_contributors()
            if contributors.totalCount > 0:
                top_contributor = next(contributors)
                # Try to get user's team membership
                try:
                    teams = self.org.get_user_teams(top_contributor)
                    if teams.totalCount > 0:
                        return f"{next(teams).name}"
                except Exception:
                    return f"user:{top_contributor.login}"

            return "default-team"  # Fallback
        except Exception:
            return "default-team"

    def create_catalog_info(self, repo_name: str, component_name: str) -> str:
        """Create Backstage catalog-info.yaml content.

        Args:
            repo_name (str): Repository name
            component_name (str): Component name for Backstage

        Returns:
            str: YAML content as string
        """
        repo = self.org.get_repo(repo_name)
        
        # Get repository description
        description = repo.description or f'Auto-generated component for {repo_name}'
        
        # Determine component specifications
        component_type = self._determine_component_type(repo)
        lifecycle = self._determine_lifecycle(repo)
        owner = self._determine_owner(repo)
        
        # Additional metadata from repo
        tags = []
        if repo.language:
            tags.append(repo.language.lower())
        if repo.topics:
            tags.extend(repo.topics)
        
        catalog_content = {
            'apiVersion': 'backstage.io/v1alpha1',
            'kind': 'Component',
            'metadata': {
                'name': component_name,
                'description': description,
                'annotations': {
                    'github.com/project-slug': f'{self.org.login}/{repo_name}',
                    'github.com/project-visibility': 'public' if not repo.private else 'private'
                },
                'tags': tags
            },
            'spec': {
                'type': component_type,
                'lifecycle': lifecycle,
                'owner': owner,
                'system': repo.topics[0] if repo.topics else 'default-system'
            }
        }
        return yaml.dump(catalog_content)

    def create_pr_and_issue(self, repo_name: str) -> Tuple[Any, Any]:
        """Create pull request and linked issue for Backstage integration.

        Args:
            repo_name (str): Repository name

        Returns:
            Tuple[PullRequest, Issue]: Created PR and Issue objects
        """
        repo = self.org.get_repo(repo_name)
        branch_name = f"backstage-integration-{int(time.time())}"
        
        # Create new branch
        source = repo.get_branch(self.base_branch)
        repo.create_git_ref(f"refs/heads/{branch_name}", source.commit.sha)

        # Create catalog entities (both Component and APIs)
        entities = self.create_catalog_entities(repo_name, repo_name)
        
        # Create catalog-info.yaml with all entities
        combined_content = "\n---\n".join(entities)
        repo.create_file(
            "catalog-info.yaml",
            "Add Backstage catalog entities",
            combined_content,
            branch=branch_name
        )

        # Create GitHub Actions workflow directory and file
        workflow_content = """name: Publish to Backstage

on:
  push:
    branches:
      - main
    paths:
      - 'catalog-info.yaml'
  workflow_dispatch:

jobs:
  publish:
    uses: ${{ github.repository_owner }}/backstage-github/.github/workflows/publish-backstage-reusable.yml@main
    with:
      repository: ${{ github.event.repository.name }}
    secrets:
      AUTOMATION_TOKEN: ${{ secrets.AUTOMATION_TOKEN }}
      BACKSTAGE_URL: ${{ secrets.BACKSTAGE_URL }}
      GITHUB_API_URL: ${{ secrets.GITHUB_API_URL }}
"""
        
        # Create .github/workflows directory if it doesn't exist
        try:
            repo.get_contents(".github/workflows")
        except Exception:
            try:
                repo.get_contents(".github")
            except Exception:
                repo.create_file(
                    ".github/README.md",
                    "Add .github directory",
                    "GitHub configuration files",
                    branch=branch_name
                )
            repo.create_file(
                ".github/workflows/README.md",
                "Add workflows directory",
                "GitHub Actions workflow files",
                branch=branch_name
            )

        # Create the workflow file
        repo.create_file(
            ".github/workflows/publish-backstage.yml",
            "Add Backstage publish workflow",
            workflow_content,
            branch=branch_name
        )

        # Create PR
        pr_body = """This PR adds Backstage integration:

1. Adds `catalog-info.yaml` containing:
   - Component registration
   - API entities (if OpenAPI/AsyncAPI/GraphQL specs are found)
2. Adds GitHub Actions workflow to automatically publish updates to Backstage

After merging this PR:
- The component and APIs will be automatically registered in Backstage
- API documentation will be available in Backstage (if API specs exist)
- Future updates to `catalog-info.yaml` will be automatically published
- You can manually trigger publishing using the Actions tab

Required setup:
1. Add `BACKSTAGE_URL` secret in repository settings
2. Ensure GitHub Actions has necessary permissions

Note: API entities are automatically generated from:
- OpenAPI/Swagger specifications
- AsyncAPI specifications
- GraphQL schemas"""

        pr = repo.create_pull(
            title="Add Backstage Integration",
            body=pr_body,
            head=branch_name,
            base=self.base_branch
        )

        # Create Issue with force merge command
        issue_body = f"""Please review and merge PR #{pr.number} for Backstage integration.

This PR adds:
1. Backstage component registration file (catalog-info.yaml)
2. Automated publishing workflow

Required actions:
1. Review the changes in PR #{pr.number}
2. Add the `BACKSTAGE_URL` secret in repository settings
3. To force merge this PR (this will override branch protection):
   Add a comment with `/force-merge`

Note: Force merge should only be used after proper review and secret configuration."""

        issue = repo.create_issue(
            title="Review and Merge Backstage Integration",
            body=issue_body,
            labels=["backstage-integration"]
        )

        return pr, issue

    def publish_to_backstage(self, backstage_url: str, catalog_info: str, backstage_token: str = None, token_type: str = "Bearer") -> bool:
        """Publish component to Backstage catalog.

        Args:
            backstage_url (str): Backstage instance URL
            catalog_info (str): Catalog info YAML content
            backstage_token (str, optional): Backstage API token. If not provided, will try to get from environment
            token_type (str, optional): Token type for authentication. Defaults to "Bearer"

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If no Backstage token is available
        """
        # Get token from parameter or environment
        token = backstage_token or os.environ.get('BACKSTAGE_TOKEN')
        if not token:
            raise ValueError("Backstage API token is required. Set BACKSTAGE_TOKEN environment variable or pass token parameter.")

        # Use token type from environment or default
        auth_type = os.environ.get('BACKSTAGE_TOKEN_TYPE', token_type)
        
        headers = {
            'Content-Type': 'application/yaml',
            'User-Agent': 'Backstage-Automation',
            'Authorization': f'{auth_type} {token}'
        }

        try:
            # Validate YAML before sending
            yaml.safe_load(catalog_info)
            
            response = requests.post(
                f"{backstage_url}/api/catalog/locations",
                data=catalog_info,
                headers=headers,
                timeout=30  # 30 seconds timeout
            )
            
            if response.status_code == 200:
                print(f"Successfully published to Backstage: {response.json()}")
                return True
            else:
                print(f"Failed to publish to Backstage. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except yaml.YAMLError as e:
            print(f"Invalid YAML content: {str(e)}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {str(e)}")
            return False
        except Exception as e:
            print(f"Unexpected error publishing to Backstage: {str(e)}")
            return False

    def publish_raw_to_backstage(self, backstage_url: str, catalog_path: str) -> bool:
        """Publish component to Backstage catalog using raw file path.

        Args:
            backstage_url (str): Backstage instance URL
            catalog_path (str): Path to the catalog-info.yaml file

        Returns:
            bool: True if successful, False otherwise
        """
        headers = {
            'Content-Type': 'application/yaml',
            'User-Agent': 'Backstage-Automation'
        }

        try:
            # Read and validate YAML file
            with open(catalog_path, 'r') as f:
                catalog_content = f.read()
            yaml.safe_load(catalog_content)  # Validate YAML syntax
            
            # Make raw API call to Backstage
            response = requests.post(
                f"{backstage_url}/api/catalog/locations",
                data=catalog_content,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                print(f"Successfully published to Backstage: {response.json()}")
                return True
            else:
                print(f"Failed to publish to Backstage. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
        except yaml.YAMLError as e:
            print(f"Invalid YAML file: {str(e)}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {str(e)}")
            return False
        except Exception as e:
            print(f"Unexpected error publishing to Backstage: {str(e)}")
            return False

    def create_github_app(self, app_name: str, webhook_url: str) -> Dict[str, Any]:
        """Create GitHub App manifest for Backstage integration.

        Args:
            app_name (str): Name for the GitHub App
            webhook_url (str): Webhook URL for the app

        Returns:
            Dict[str, Any]: GitHub App manifest
        """
        app_manifest = {
            "name": app_name,
            "url": webhook_url,
            "hook_attributes": {
                "url": f"{webhook_url}/api/github/webhook"
            },
            "permissions": {
                "contents": "write",
                "metadata": "read",
                "pull_requests": "write",
                "issues": "write",
                "administration": "write"  # Required for branch protection override
            },
            "events": [
                "issues",
                "issue_comment",
                "pull_request"
            ]
        }
        return app_manifest

    def force_merge_pr(self, repo_name: str, pr_number: int) -> bool:
        """Force merge a PR by temporarily disabling branch protection.

        Args:
            repo_name (str): Repository name
            pr_number (int): Pull request number

        Returns:
            bool: True if merge successful, False otherwise
        """
        repo = self.org.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        branch = pr.base.ref
        
        try:
            # Get current branch protection
            protection = None
            try:
                protection = repo.get_branch(branch).get_protection()
            except Exception:
                # Branch might not have protection
                pass

            if protection:
                # Temporarily disable branch protection
                repo.get_branch(branch).remove_protection()

            # Merge the PR
            merge_result = pr.merge(
                merge_method="squash",
                commit_title=f"Force merge PR #{pr_number} [skip ci]",
                commit_message="Force merged via Backstage automation"
            )

            if protection:
                # Restore branch protection
                repo.get_branch(branch).edit_protection(
                    strict=True,
                    contexts=[],
                    enforce_admins=True,
                    dismissal_users=[],
                    dismissal_teams=[],
                    dismiss_stale_reviews=True,
                    require_code_owner_reviews=True
                )

            return merge_result.merged

        except Exception as e:
            print(f"Error force merging PR: {str(e)}")
            return False

    def generate_status_report(self) -> str:
        """Generate a status report for GitHub Actions."""
        total = onboarded = in_progress = not_onboarded = 0
        repositories = self.org.get_repos()
        
        for repo in repositories:
            total += 1
            try:
                try:
                    repo.get_contents("catalog-info.yaml")
                    onboarded += 1
                    self.status_report.append(f"✅ {repo.name}: Onboarded")
                    continue
                except Exception:
                    pass

                # Check for open PRs
                open_prs = repo.get_pulls(state='open')
                has_pr = False
                for pr in open_prs:
                    if "backstage-integration" in pr.head.ref:
                        in_progress += 1
                        has_pr = True
                        self.status_report.append(f"🔄 {repo.name}: In Progress (PR #{pr.number})")
                        break
                
                if not has_pr:
                    not_onboarded += 1
                    self.status_report.append(f"❌ {repo.name}: Not Onboarded")
                
            except Exception as e:
                self.status_report.append(f"⚠️ {repo.name}: Error - {str(e)}")

        # Generate summary
        summary = [
            f"## Status Summary ({datetime.now().strftime('%Y-%m-%d %H:%M UTC')})",
            f"- Total Repositories: {total}",
            f"- ✅ Onboarded: {onboarded}",
            f"- 🔄 In Progress: {in_progress}",
            f"- ❌ Not Onboarded: {not_onboarded}",
            "",
            "## Repository Details:",
            *self.status_report
        ]
        
        return "\n".join(summary)

    def analyze_repository_priority(self, repo: Any) -> Dict[str, Any]:
        """Analyze a repository to determine its priority for Backstage integration.

        Args:
            repo: GitHub repository object

        Returns:
            Dict[str, Any]: Analysis results with score and reasons
        """
        score = 0
        reasons = []

        # Activity metrics
        if (datetime.now() - repo.pushed_at).days <= 30:  # Updated in last 30 days
            score += 30
            reasons.append("Recently active")

        if (datetime.now() - repo.created_at).days >= 180:  # Established project (>6 months)
            score += 20
            reasons.append("Established project")

        # Popularity metrics
        if repo.stargazers_count > 0:
            score += min(repo.stargazers_count * 2, 50)  # Up to 50 points for stars
            reasons.append(f"Has {repo.stargazers_count} stars")

        if repo.forks_count > 0:
            score += min(repo.forks_count * 5, 50)  # Up to 50 points for forks
            reasons.append(f"Has {repo.forks_count} forks")

        # Developer-facing indicators
        try:
            files = [f.name for f in repo.get_contents("")]
            dev_files = ["README.md", "API.md", "docs", "api", "swagger.yml", "openapi.yml"]
            matches = [f for f in files if any(df.lower() in f.lower() for df in dev_files)]
            if matches:
                score += 30
                reasons.append("Has developer documentation")

            # Check for API/SDK keywords in description and topics
            api_keywords = ["api", "sdk", "library", "client", "developer", "toolkit"]
            if repo.description and any(k in repo.description.lower() for k in api_keywords):
                score += 20
                reasons.append("API/SDK-related description")

            if repo.topics and any(k in t.lower() for t in repo.topics for k in api_keywords):
                score += 20
                reasons.append("API/SDK-related topics")

        except Exception:
            pass  # Skip file analysis if failed

        # Metadata completeness
        if repo.description:
            score += 10
            reasons.append("Has description")

        if repo.homepage:
            score += 10
            reasons.append("Has homepage URL")

        if repo.topics:
            score += min(len(repo.topics) * 5, 20)  # Up to 20 points for topics
            reasons.append(f"Has {len(repo.topics)} topics")

        return {
            "name": repo.name,
            "score": score,
            "reasons": reasons,
            "url": repo.html_url,
            "description": repo.description or "",
            "updated_at": repo.pushed_at.isoformat(),
            "stars": repo.stargazers_count,
            "forks": repo.forks_count
        }

    def generate_priority_report(self) -> str:
        """Generate a report of repositories prioritized for Backstage integration.

        Returns:
            str: Markdown formatted priority report
        """
        print("Analyzing repositories for Backstage integration priority...")
        repositories = self.org.get_repos()
        analysis_results = []

        for repo in repositories:
            try:
                # Skip if already has catalog-info.yaml
                try:
                    repo.get_contents("catalog-info.yaml")
                    continue
                except Exception:
                    pass

                result = self.analyze_repository_priority(repo)
                if result["score"] > 30:  # Only include repositories with meaningful scores
                    analysis_results.append(result)

            except Exception as e:
                print(f"Error analyzing {repo.name}: {str(e)}")

        # Sort by score descending
        analysis_results.sort(key=lambda x: x["score"], reverse=True)

        # Generate markdown report
        report_lines = [
            "# Backstage Integration Priority Report",
            f"\nGenerated on: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
            "\n## Top Candidates for Backstage Integration\n"
        ]

        for idx, result in enumerate(analysis_results[:10], 1):
            report_lines.extend([
                f"### {idx}. {result['name']} (Score: {result['score']})",
                f"- URL: {result['url']}",
                f"- Description: {result['description']}",
                f"- Last Updated: {result['updated_at']}",
                f"- Stars: {result['stars']}, Forks: {result['forks']}",
                "\nRecommendation reasons:",
                "".join([f"\n- {reason}" for reason in result['reasons']]),
                "\n"
            ])

        return "\n".join(report_lines)

    def _detect_api_specs(self, repo: Any) -> List[Dict[str, str]]:
        """Detect API specifications in the repository.

        Args:
            repo: GitHub repository object

        Returns:
            List[Dict[str, str]]: List of API specs with their paths and types
        """
        api_specs = []
        spec_patterns = [
            "openapi.yaml", "openapi.yml", "openapi.json",
            "swagger.yaml", "swagger.yml", "swagger.json",
            "asyncapi.yaml", "asyncapi.yml", "asyncapi.json",
            "graphql.schema", "schema.graphql"
        ]
        
        try:
            contents = repo.get_contents("")
            for content in contents:
                if content.type == "dir":
                    try:
                        # Check docs, api, specs directories
                        if content.name.lower() in ["docs", "api", "specs"]:
                            subcontents = repo.get_contents(content.path)
                            for subcontent in subcontents:
                                if any(subcontent.name.lower().endswith(pat) for pat in spec_patterns):
                                    api_specs.append({
                                        "path": subcontent.path,
                                        "type": self._determine_api_type(subcontent.name),
                                        "content": subcontent.decoded_content.decode()
                                    })
                    except Exception:
                        continue
                elif any(content.name.lower().endswith(pat) for pat in spec_patterns):
                    api_specs.append({
                        "path": content.path,
                        "type": self._determine_api_type(content.name),
                        "content": content.decoded_content.decode()
                    })
        except Exception as e:
            print(f"Error detecting API specs: {str(e)}")
        
        return api_specs

    def _determine_api_type(self, filename: str) -> str:
        """Determine API type from filename.
        
        Args:
            filename (str): Name of the API specification file
            
        Returns:
            str: API type (openapi, asyncapi, graphql)
        """
        filename = filename.lower()
        if "openapi" in filename or "swagger" in filename:
            return "openapi"
        elif "asyncapi" in filename:
            return "asyncapi"
        elif "graphql" in filename:
            return "graphql"
        return "openapi"  # default to OpenAPI

    def create_api_entity(self, repo_name: str, api_spec: Dict[str, str]) -> str:
        """Create Backstage API entity YAML content.
        
        Args:
            repo_name (str): Repository name
            api_spec (Dict[str, str]): API specification details
            
        Returns:
            str: YAML content for API entity
        """
        api_content = {
            'apiVersion': 'backstage.io/v1alpha1',
            'kind': 'API',
            'metadata': {
                'name': f"{repo_name}-api",
                'description': f'API for {repo_name}',
                'annotations': {
                    'github.com/project-slug': f'{self.org.login}/{repo_name}',
                    'backstage.io/source-location': f'url:https://github.com/{self.org.login}/{repo_name}/blob/main/{api_spec["path"]}'
                }
            },
            'spec': {
                'type': api_spec['type'],
                'lifecycle': 'production',
                'owner': 'default-team',
                'definition': api_spec['content']
            }
        }
        return yaml.dump(api_content)

    def create_catalog_entities(self, repo_name: str, component_name: str) -> List[str]:
        """Create all necessary catalog entities (Component and APIs).
        
        Args:
            repo_name (str): Repository name
            component_name (str): Component name for Backstage
            
        Returns:
            List[str]: List of YAML contents for all entities
        """
        repo = self.org.get_repo(repo_name)
        entities = []

        # Create component entity
        component_yaml = self.create_catalog_info(repo_name, component_name)
        entities.append(component_yaml)

        # Look for API specs and create API entities
        api_specs = self._detect_api_specs(repo)
        for api_spec in api_specs:
            api_yaml = self.create_api_entity(repo_name, api_spec)
            entities.append(api_yaml)

        return entities

def main():
    """Main function to run the automation for all repositories in the organization."""
    # Configuration
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise ValueError("GITHUB_TOKEN environment variable is required")
    
    org_name = os.environ.get("GITHUB_ORG")
    if not org_name:
        raise ValueError("GITHUB_ORG environment variable is required")
    
    backstage_url = os.environ.get("BACKSTAGE_URL")
    if not backstage_url:
        raise ValueError("BACKSTAGE_URL environment variable is required")

    github_api_url = os.environ.get("GITHUB_API_URL")  # Optional
    check_only = os.environ.get("CHECK_ONLY", "false").lower() == "true"
    canary_repo = os.environ.get("CANARY_REPO")  # Optional single repository for testing

    automation = BackstageAutomation(github_token, org_name, github_api_url)
    
    try:
        if check_only:
            # Generate status report only
            status_report = automation.generate_status_report()
            with open("status_report.txt", "w") as f:
                f.write(status_report)
            print("Status report generated.")
            return

        # Get repositories to process
        print(f"Fetching repositories from organization {org_name}...")
        if canary_repo:
            print(f"Running in canary mode for repository: {canary_repo}")
            try:
                repositories = [automation.org.get_repo(canary_repo)]
            except Exception as e:
                print(f"Error: Could not find repository {canary_repo}: {str(e)}")
                return
        else:
            repositories = automation.org.get_repos()
        
        processed = skipped = failed = 0
        
        for repo in repositories:
            try:
                print(f"\nProcessing repository: {repo.name}")
                
                # Skip if catalog-info.yaml already exists in any branch
                try:
                    repo.get_contents("catalog-info.yaml")
                    print(f"Skipping {repo.name}: catalog-info.yaml already exists")
                    skipped += 1
                    continue
                except Exception:
                    pass  # File doesn't exist, continue with creation

                # Create PR and Issue
                pr, issue = automation.create_pr_and_issue(repo.name)
                print(f"Created PR #{pr.number} for {repo.name}")
                processed += 1

            except Exception as repo_error:
                print(f"Error processing repository {repo.name}: {str(repo_error)}")
                failed += 1
                continue

        # Generate summary
        summary = [
            f"## Automation Summary ({datetime.now().strftime('%Y-%m-%d %H:%M UTC')})",
            "### Mode: {}".format("Canary Test" if canary_repo else "Full Organization"),
            f"- Repository: {canary_repo}" if canary_repo else f"- Organization: {org_name}",
            f"- Processed: {processed} repositories",
            f"- Skipped: {skipped} repositories (already onboarded)",
            f"- Failed: {failed} repositories",
        ]
        
        with open("automation_summary.txt", "w") as f:
            f.write("\n".join(summary))

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    main()
