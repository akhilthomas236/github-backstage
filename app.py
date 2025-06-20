import streamlit as st
import pandas as pd
from backstage_automation import BackstageAutomation
from secure_storage import SecureStorage
import os
import time
from typing import Dict, List
import random

# Page configuration
st.set_page_config(
    page_title="Backstage Automation",
    page_icon="🚀",
    layout="wide"
)

# Initialize secure storage
storage = SecureStorage()

# Demo data for test organization
DEMO_REPOS = [
    {"name": "frontend-app", "language": "TypeScript", "status": "Onboarded"},
    {"name": "backend-service", "language": "Python", "status": "In Progress"},
    {"name": "data-pipeline", "language": "Python", "status": "Not Onboarded"},
    {"name": "documentation", "language": "MDX", "status": "Onboarded"},
    {"name": "infrastructure", "language": "HCL", "status": "Failed"},
    {"name": "mobile-app", "language": "Kotlin", "status": "Not Onboarded"},
    {"name": "analytics-service", "language": "Python", "status": "Onboarded"},
    {"name": "monitoring-tools", "language": "Go", "status": "In Progress"}
]

def get_demo_data():
    """Generate demo repository data with realistic statistics."""
    data = []
    for repo in DEMO_REPOS:
        status_details = {
            "Repository": repo["name"],
            "Language": repo["language"],
            "Status": repo["status"],
            "Has catalog-info.yaml": "Yes" if repo["status"] == "Onboarded" else "No",
            "PR Status": "Merged" if repo["status"] == "Onboarded" else 
                        "PR #123 Open" if repo["status"] == "In Progress" else
                        "N/A",
            "Last Updated": f"{random.randint(1, 30)} days ago"
        }
        data.append(status_details)
    return pd.DataFrame(data)

def init_automation(github_token: str, org_name: str, backstage_url: str, github_api_url: str = None) -> BackstageAutomation:
    """Initialize the BackstageAutomation class with provided credentials."""
    try:
        return BackstageAutomation(github_token, org_name, github_api_url)
    except Exception as e:
        st.error(f"Failed to initialize automation: {str(e)}")
        return None

def get_repo_status(automation: BackstageAutomation) -> List[Dict]:
    """Get the status of all repositories in the organization."""
    repos_status = []
    
    try:
        repositories = automation.org.get_repos()
        for repo in repositories:
            status = {
                "Repository": repo.name,
                "Language": repo.language or "Unknown",
                "Status": "Not Onboarded",
                "Has catalog-info.yaml": "No",
                "PR Status": "N/A",
                "Last Updated": repo.updated_at.strftime("%Y-%m-%d")
            }
            
            try:
                # Check if catalog-info.yaml exists
                try:
                    repo.get_contents("catalog-info.yaml")
                    status["Has catalog-info.yaml"] = "Yes"
                    status["Status"] = "Onboarded"
                except Exception:
                    pass
                
                # Check for open PRs related to Backstage
                open_prs = repo.get_pulls(state='open')
                for pr in open_prs:
                    if "backstage-integration" in pr.head.ref:
                        status["Status"] = "In Progress"
                        status["PR Status"] = f"PR #{pr.number} Open"
                        break
                
            except Exception as e:
                status["Status"] = f"Error: {str(e)}"
            
            repos_status.append(status)
    
    except Exception as e:
        st.error(f"Failed to fetch repositories: {str(e)}")
    
    return repos_status

def render_org_dashboard(org_name: str, is_demo: bool = False):
    """Render the dashboard for a specific organization."""
    if is_demo:
        df = get_demo_data()
    else:
        config = storage.load_org_config(org_name)
        if not config:
            st.error(f"No configuration found for {org_name}")
            return
        
        automation = init_automation(
            config["github_token"],
            org_name,
            config["backstage_url"],
            config.get("github_api_url")
        )
        
        if not automation:
            return
        
        repos_status = get_repo_status(automation)
        df = pd.DataFrame(repos_status)
    
    # Display statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Repositories", len(df))
    with col2:
        onboarded = len(df[df["Status"] == "Onboarded"])
        st.metric("Onboarded", onboarded)
    with col3:
        in_progress = len(df[df["Status"] == "In Progress"])
        st.metric("In Progress", in_progress)
    with col4:
        not_onboarded = len(df[df["Status"] == "Not Onboarded"])
        st.metric("Not Onboarded", not_onboarded)
    
    # Display repository table
    st.dataframe(
        df,
        column_config={
            "Repository": st.column_config.TextColumn("Repository"),
            "Language": st.column_config.TextColumn("Language"),
            "Status": st.column_config.TextColumn(
                "Status",
                help="Current onboarding status"
            ),
            "Has catalog-info.yaml": st.column_config.TextColumn("Has catalog-info.yaml"),
            "PR Status": st.column_config.TextColumn("PR Status"),
            "Last Updated": st.column_config.TextColumn("Last Updated")
        },
        hide_index=True
    )
    
    # Repository selection for onboarding
    not_onboarded = df[df["Status"] == "Not Onboarded"]["Repository"].tolist()
    if not_onboarded:
        st.subheader("Onboard New Repositories")
        selected_repos = st.multiselect(
            "Select repositories to onboard",
            options=not_onboarded
        )
        
        if st.button("Start Onboarding"):
            if selected_repos:
                if not is_demo:
                    for repo_name in selected_repos:
                        try:
                            pr, issue = automation.create_pr_and_issue(repo_name)
                            st.success(f"Created PR #{pr.number} for {repo_name}")
                        except Exception as e:
                            st.error(f"Failed to onboard {repo_name}: {str(e)}")
                else:
                    st.info("Demo mode: Onboarding simulation successful!")
            else:
                st.warning("Please select at least one repository.")

# Sidebar - Organization Management
with st.sidebar:
    st.title("Organizations")
    
    # Add new organization
    with st.expander("Add New Organization"):
        with st.form("new_org_form"):
            new_org_name = st.text_input("Organization Name")
            github_token = st.text_input("GitHub Token", type="password")
            backstage_url = st.text_input("Backstage URL")
            github_api_url = st.text_input(
                "GitHub API URL (Optional)",
                placeholder="e.g., https://github.enterprise.com/api/v3"
            )
            
            if st.form_submit_button("Add Organization"):
                if new_org_name and github_token and backstage_url:
                    config = {
                        "github_token": github_token,
                        "backstage_url": backstage_url,
                        "github_api_url": github_api_url if github_api_url else None
                    }
                    storage.save_org_config(new_org_name, config)
                    st.success(f"Organization {new_org_name} added successfully!")
                else:
                    st.error("Please fill in all required fields.")

# Main content
st.title("🚀 Backstage Integration Dashboard")

# Get list of organizations
orgs = storage.list_organizations()
orgs.append("Demo Organization")  # Add demo organization

if not orgs:
    st.info("No organizations configured. Add one from the sidebar!")
else:
    # Create tabs for each organization
    tabs = st.tabs(orgs)
    for i, tab in enumerate(tabs):
        with tab:
            org_name = orgs[i]
            if org_name == "Demo Organization":
                render_org_dashboard(org_name, is_demo=True)
            else:
                render_org_dashboard(org_name)
