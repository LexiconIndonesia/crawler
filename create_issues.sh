#!/bin/bash

# Script to create GitHub issues from Issue.md and add them to Lexicon project
# Usage: ./create_issues.sh

# Note: Not using 'set -e' so we can continue even if some issues fail

ISSUE_FILE="Issue.md"
PROJECT_NAME="Lexicon"
REPO_OWNER=$(gh repo view --json owner -q .owner.login)
REPO_NAME=$(gh repo view --json name -q .name)

# Project and field IDs for setting System field
PROJECT_ID="PVT_kwDOCIry5M4BGboS"
SYSTEM_FIELD_ID="PVTSSF_lADOCIry5M4BGboSzg3e2Vw"
CRAWLER_OPTION_ID="1abb5d89"

# Track success/failure counts
TOTAL_ISSUES=0
SUCCESSFUL_ISSUES=0
FAILED_ISSUES=0

echo "Creating issues for repository: $REPO_OWNER/$REPO_NAME"
echo "Project: $PROJECT_NAME"
echo ""

# Check if Issue.md exists
if [ ! -f "$ISSUE_FILE" ]; then
    echo "Error: $ISSUE_FILE not found!"
    exit 1
fi

# Get project number
echo "Finding project '$PROJECT_NAME'..."
PROJECT_NUMBER=$(gh project list --owner "$REPO_OWNER" --format json | jq -r ".projects[] | select(.title == \"$PROJECT_NAME\") | .number")

if [ -z "$PROJECT_NUMBER" ]; then
    echo "Error: Project '$PROJECT_NAME' not found!"
    echo "Available projects:"
    gh project list --owner "$REPO_OWNER"
    exit 1
fi

echo "Found project #$PROJECT_NUMBER"
echo ""

# Create labels if they don't exist
echo "Ensuring required labels exist..."
gh label create "size: Small" --color "0e8a16" --description "Small sized task" 2>/dev/null || true
gh label create "size: Medium" --color "fbca04" --description "Medium sized task" 2>/dev/null || true
gh label create "size: Large" --color "d93f0b" --description "Large sized task" 2>/dev/null || true
gh label create "priority: High" --color "b60205" --description "High priority" 2>/dev/null || true
gh label create "priority: Medium" --color "ff9800" --description "Medium priority" 2>/dev/null || true
gh label create "priority: Low" --color "c5def5" --description "Low priority" 2>/dev/null || true
echo "✓ Labels ready"
echo ""

# Parse Issue.md and create issues
issue_number=""
title=""
description=""
acceptance_criteria=""
size=""
priority=""
body=""

create_issue() {
    if [ -n "$title" ] && [ -n "$description" ]; then
        TOTAL_ISSUES=$((TOTAL_ISSUES + 1))
        echo "Creating: $title"

        # Build issue body
        body="$description

## Acceptance Criteria

$acceptance_criteria

---

**Size:** $size | **Priority:** $priority"

        # Create labels for size and priority
        size_label="size: $size"
        priority_label="priority: $priority"

        # Create issue and capture the issue number
        if issue_url=$(gh issue create \
            --title "$title" \
            --body "$body" \
            --label "$size_label" \
            --label "$priority_label" 2>&1); then

            # Extract issue number from URL
            created_issue_number=$(echo "$issue_url" | grep -oE '[0-9]+$')

            if [ -n "$created_issue_number" ]; then
                echo "  ✓ Created issue #$created_issue_number"

                # Add to project
                if project_output=$(gh project item-add "$PROJECT_NUMBER" \
                    --owner "$REPO_OWNER" \
                    --url "https://github.com/$REPO_OWNER/$REPO_NAME/issues/$created_issue_number" \
                    --format json 2>&1); then
                    echo "  ✓ Added to project '$PROJECT_NAME'"

                    # Extract the project item ID from the output
                    project_item_id=$(echo "$project_output" | jq -r '.id')

                    if [ -n "$project_item_id" ] && [ "$project_item_id" != "null" ]; then
                        # Set System field to "Crawler"
                        if gh project item-edit \
                            --id "$project_item_id" \
                            --project-id "$PROJECT_ID" \
                            --field-id "$SYSTEM_FIELD_ID" \
                            --single-select-option-id "$CRAWLER_OPTION_ID" 2>/dev/null; then
                            echo "  ✓ Set System to 'Crawler'"
                        else
                            echo "  ⚠ Could not set System field"
                        fi
                    fi

                    SUCCESSFUL_ISSUES=$((SUCCESSFUL_ISSUES + 1))
                else
                    echo "  ✗ ERROR adding to project: $project_output"
                    FAILED_ISSUES=$((FAILED_ISSUES + 1))
                fi
            else
                echo "  ✗ ERROR: Could not extract issue number from: $issue_url"
                FAILED_ISSUES=$((FAILED_ISSUES + 1))
            fi
        else
            echo "  ✗ ERROR creating issue: $issue_url"
            echo "  Title: $title"
            echo "  Labels: $size_label, $priority_label"
            FAILED_ISSUES=$((FAILED_ISSUES + 1))
        fi

        echo ""

        # Small delay to avoid rate limiting
        sleep 1
    fi
}

# Read and parse Issue.md
while IFS= read -r line; do
    # Match issue title: ### Issue #N: Title
    if [[ $line =~ ^###\ Issue\ #([0-9]+):\ (.+)$ ]]; then
        # Create previous issue before starting new one
        create_issue

        # Start new issue
        issue_number="${BASH_REMATCH[1]}"
        title="${BASH_REMATCH[2]}"
        description=""
        acceptance_criteria=""
        size=""
        priority=""
        in_acceptance=false

    # Match description
    elif [[ $line =~ ^\*\*Description\*\*:\ (.+)$ ]]; then
        description="${BASH_REMATCH[1]}"
        in_acceptance=false

    # Match acceptance criteria header
    elif [[ $line =~ ^\*\*Acceptance\ Criteria\*\*: ]]; then
        in_acceptance=true

    # Match acceptance criteria items
    elif [[ $in_acceptance == true ]] && [[ $line =~ ^-\ \[\ \]\ (.+)$ ]]; then
        if [ -n "$acceptance_criteria" ]; then
            acceptance_criteria="$acceptance_criteria
- [ ] ${BASH_REMATCH[1]}"
        else
            acceptance_criteria="- [ ] ${BASH_REMATCH[1]}"
        fi

    # Match size and priority
    elif [[ $line =~ ^\*\*Size\*\*:\ ([^|]+)\ \|\ \*\*Priority\*\*:\ (.+)$ ]]; then
        size=$(echo "${BASH_REMATCH[1]}" | xargs)
        priority=$(echo "${BASH_REMATCH[2]}" | xargs)
        in_acceptance=false

    # Match separator (end of issue)
    elif [[ $line =~ ^---$ ]]; then
        in_acceptance=false
    fi

done < "$ISSUE_FILE"

# Create the last issue
create_issue

# Print summary
echo "========================================"
echo "Summary:"
echo "  Total issues: $TOTAL_ISSUES"
echo "  Successful: $SUCCESSFUL_ISSUES"
echo "  Failed: $FAILED_ISSUES"
echo "========================================"
echo ""

if [ $FAILED_ISSUES -eq 0 ]; then
    echo "✓ All issues created successfully!"
else
    echo "⚠ Some issues failed to create. See errors above."
fi

echo ""
echo "View your issues: gh issue list"
echo "View your project: gh project view $PROJECT_NUMBER --owner $REPO_OWNER"

# Exit with error code if any issues failed
if [ $FAILED_ISSUES -gt 0 ]; then
    exit 1
fi
