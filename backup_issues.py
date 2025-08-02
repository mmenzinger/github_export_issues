import json, os, jinja2, re, requests, html
from github import Github, Auth
from markdown import markdown
from datetime import datetime
# secret token for GitHub API access
# Make sure to replace the token with your own GitHub personal access token
# API_TOKEN = "your_github_token_here"
# and an *active* session cookie for GitHub
# SESSION_COOKIE = "your_github_user_session_cookie_here"
# and add a list of repositories you want to backup
# REPOS_TO_BACKUP = ["repo1", "repo2", ...]
from settings import API_TOKEN, REPOS_TO_BACKUP, SESSION_COOKIE


ISSUES_FOLDER = "issues"
ISSUE_FOLDER = f"{ISSUES_FOLDER}/[repo_name]"
ISSUE_ASSETS_FOLDER = f"{ISSUE_FOLDER}/assets"
ISSUE_CACHE_FOLDER = f"{ISSUE_FOLDER}/cache"
ISSUE_USER_CACHE = f"{ISSUE_CACHE_FOLDER}/users.json"
ISSUE_DATETIME_CACHE = f"{ISSUE_CACHE_FOLDER}/datetime.json"
ISSUES_CACHE_FILES = f"{ISSUE_CACHE_FOLDER}/[issue_number].json"
ISSUE_RAW_FILE = f"{ISSUE_FOLDER}/issues_raw.json"
ISSUE_PARSED_FILE = f"{ISSUE_FOLDER}/issues_parsed.json"
TEMPLATES_FOLDER = "templates"
TEMPLATE_FILE = "template.html"
TEMPLATE_RELATIVE_ASSETS_FOLDER = "assets"
GITHUB_ASSETS_PATH = "https://github.com/"


################################################################################
# helper functions
################################################################################
def makepath(path, replace = {}):
    for key, value in replace.items():
        path = path.replace(key, value)
    return path

def fixDictNumericKeys(dict):
    # convert keys to int
    return {int(k): v for k, v in dict.items() if k.isdigit()}

def jsonLoadDict(file):
    dict = json.load(file)
    return fixDictNumericKeys(dict)

def strToDateTime(date_str):
    # convert string to datetime object
    return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ') if date_str else None

def parseBody(text):
    return markdown(html.escape(text), extensions=['nl2br'])

def extractUser(user, data):
    if user['id'] not in data['users']:
        data['users'][user['id']] = user
    return user['id']

def extractAssets(content, replace):
    # this ignores private images, which are not accessible without authentication
    # example: eduvidual-infrastructure #1792
    try:
        if content is None:
            return
        imgs = []
        res = re.findall(fr'!\[Image\]\(({GITHUB_ASSETS_PATH}.*?)\)', content, flags = re.IGNORECASE)
        imgs.extend(res)
        res = re.findall(fr'<img.*?src="({GITHUB_ASSETS_PATH}.*?)".*?>', content, flags = re.IGNORECASE)
        imgs.extend(res)
        if len(imgs):
            assets_folder = makepath(ISSUE_ASSETS_FOLDER, replace)
            os.makedirs(assets_folder, exist_ok=True)
            for img in imgs:
                # download image and save it to assets folder
                # based on https://stackoverflow.com/questions/76666026/download-github-pull-request-description-images-remotely-or-via-the-api
                # images are always converted to png by github? (verification needed)
                img_name = os.path.basename(img)
                img_path = f"{assets_folder}/{img_name}.png"
                if not os.path.exists(img_path):
                    print(f"Downloading image {img}")
                    with open(img_path, 'wb') as img_file:
                        img_file.write(requests.get(f"{img}", headers={
                            "cookie": f"user_session={SESSION_COOKIE};"
                        }).content)
                else:
                    print(f"Image {img_name} already exists, skipping download.")
    except Exception as e:
        print(e)
        print(content)

def replaceAssets(content):
    # replace image links in content with local paths
    def replaceLocalImage(match):
        img_name = os.path.basename(match.group(1))
        return f'![Image]({TEMPLATE_RELATIVE_ASSETS_FOLDER}/{img_name}.png)'
    # replace online image links with their original URL
    def replaceOnlineImage(match):
        return f'![Image]({match.group(1)})'
    content = re.sub(fr'!\[Image\]\(({GITHUB_ASSETS_PATH}.*?)\)', replaceLocalImage, content, flags = re.IGNORECASE)
    content = re.sub(fr'<img.*?src="({GITHUB_ASSETS_PATH}.*?)".*?>', replaceLocalImage, content, flags = re.IGNORECASE)
    content = re.sub(fr'<img.*?src="(.*?)".*?>', replaceOnlineImage, content, flags = re.IGNORECASE)
    content = re.sub(fr'<img.*?src=([^ >]*).*?>', replaceOnlineImage, content, flags = re.IGNORECASE)
    return content

def replaceUser(user_id, data):
    # replace user id with user login in content
    id = user_id
    if id in data['users']:
        return data['users'][id]['login']
    return f"User-{id}"  # Fallback if user not found

def replaceDateTime(date_str):
    datetime_obj = datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')
    return datetime_obj.strftime('%d.%m.%Y')

#################################################################################
# load raw data from GitHub and save to JSON files
#################################################################################
def loadRawData():
    auth = Auth.Token(API_TOKEN)
    g = Github(auth=auth)

    for repo in g.get_user().get_repos():
        if(repo.name in REPOS_TO_BACKUP):
            print(f"Backing up issues for {repo.name}...")
            replace = {
                "[repo_name]": repo.name,
                "[issue_number]": str(0),
            }
            # create folder with repo name inside issues folder
            # os.makedirs(makepath(ISSUE_FOLDER, replace), exist_ok=True)
            os.makedirs(makepath(ISSUE_CACHE_FOLDER, replace), exist_ok=True)
            data = {
                'repo_name': repo.name,
                'issues': [],
                'users': {},
            }

            old_datetime = None
            new_datetime = g.get_rate_limit().core.reset
            datetime_file = makepath(ISSUE_DATETIME_CACHE, replace)
            if os.path.exists(datetime_file):
                with open(datetime_file, 'r') as f:
                    old_datetime = json.load(f).get('datetime')

            # read users from file if it exists
            user_cache_file = makepath(ISSUE_USER_CACHE, replace)
            if os.path.exists(user_cache_file):
                print(f"Loading user cache from {user_cache_file}")
                with open(user_cache_file, 'r') as f:
                    data['users'] = jsonLoadDict(f)

            num_users = len(data['users'])
            issue_list = None
            if old_datetime:
                issue_list = repo.get_issues(since=strToDateTime(old_datetime), state='all')
            else:
                issue_list = repo.get_issues(state='all')
            for issue in issue_list:
                replace['[issue_number]'] = str(issue.number)
                issue_file = makepath(ISSUES_CACHE_FILES, replace)
                
                #check if issue file already exists
                updated_at = None
                local_issue_data = None
                if os.path.exists(issue_file):
                    with open(issue_file, 'r') as f:
                        local_issue_data = json.load(f)
                        updated_at = strToDateTime(local_issue_data['updated_at'])

                print(f"Processing issue #{issue.number}: {issue.title[:30]} ...", end='')
                issue_data = issue.raw_data

                 # Fetch comments
                comments = local_issue_data.get('comments', []) if local_issue_data else []
                if updated_at is None or strToDateTime(issue_data['updated_at']) > updated_at:
                    if updated_at:
                        comment_list = issue.get_comments(since=updated_at)
                    else:
                        comment_list = issue.get_comments()

                    for comment in comment_list:
                        comment_data = comment.raw_data
                        comment_data['user'] = extractUser(comment_data['user'], data)
                        existing = False
                        for c in comments:
                            # if comment already exists, update it
                            if c['id'] == comment_data['id']:
                                c = comment_data
                                existing = True
                                break
                        if not existing:
                            comments.append(comment_data)

                    issue_data['comments'] = comments

                    issue_data['user'] = extractUser(issue_data['user'], data)
                    issue_data['assignee'] = extractUser(issue_data['assignee'], data) if issue_data['assignee'] else None
                    issue_data['assignees'] = [extractUser(assignee, data) for assignee in issue_data['assignees']]
                    if issue_data['closed_by']:
                        issue_data['closed_by'] = extractUser(issue_data['closed_by'], data)

                    #write issue data to file
                    with open(issue_file, 'w') as f:
                        json.dump(issue_data, f, indent=4)

                    #update new user data to file
                    if len(data['users']) > num_users:
                        print(f" {len(data['users']) - num_users} new user(s),", end='')
                        num_users = len(data['users'])
                        user_file = makepath(ISSUE_USER_CACHE, replace)
                        with open(user_file, 'w') as f:
                            json.dump(data['users'], f, indent=4)

                    print(f" {len(comments)} new/changed comment(s)")
                else:
                    print(" skipped")
            # write datetime to file at the end!
            # if this is written to early, it will skip issues if interrupted
            with open(datetime_file, 'w') as f:
                json.dump({'datetime': new_datetime.strftime('%Y-%m-%dT%H:%M:%SZ')}, f)
                
    g.close()

#################################################################################
# combine raw data into a single JSON file
#################################################################################
def combineRawData():
    # for each folder in ISSUES_FOLDER, combine all issue files into a single JSON file
    if not os.path.exists(ISSUES_FOLDER):
        print(f"Folder {ISSUES_FOLDER} does not exist. Please run download_issues.py first.")
        return
    for repo in REPOS_TO_BACKUP:
        replace = {
            '[repo_name]': repo,
        }
        if not os.path.exists(makepath(ISSUE_CACHE_FOLDER, replace)):
            print(f"Cache folder for {repo} does not exist. Skipping...")
            continue
        print(f"Combining raw data for {repo}...")
        data = {'repo_name': repo, 'issues': [], 'users': {}}
        # load user cache from file if it exists
        user_cache_file = makepath(ISSUE_USER_CACHE, replace)
        if os.path.exists(user_cache_file):
            print(f"Loading user cache from {user_cache_file}")
            with open(user_cache_file, 'r') as f:
                data['users'] = jsonLoadDict(f)
        # load issue files with the format [issue_number].json
        issues_folder = makepath(ISSUE_CACHE_FOLDER, replace)
        issues_files = [int(f.split('.')[0]) for f in os.listdir(issues_folder) if re.match(r'^\d+\.json$', f)]
        issues_files.sort(reverse=True)  # sort by issue number descending
        for issue_file in issues_files:
            with open(f"{issues_folder}/{issue_file}.json", 'r') as f:
                data['issues'].append(json.load(f))
        # write combined data to file
        combined_file = makepath(ISSUE_RAW_FILE, replace)
        print(f"Writing combined raw data to {combined_file}")
        with open(combined_file, 'w') as f:
            json.dump(data, f, indent=4)

#################################################################################
# parse issues and download assets
#################################################################################
def parseIssues():
    # for each folder in ISSUES_FOLDER, parse issues and download assets
    if not os.path.exists(ISSUES_FOLDER):
        print(f"Folder {ISSUES_FOLDER} does not exist. Please run download_issues.py first.")
        return

    for repo in REPOS_TO_BACKUP:
        replace = {
            '[repo_name]': repo,
        }
        print(f"Parsing issues for {repo}...")
        # load combined raw data from file
        raw_file = makepath(ISSUE_RAW_FILE, replace)
        if not os.path.exists(raw_file):
            print(f"Combined raw data file {raw_file} does not exist. Skipping...")
            continue
        with open(raw_file, 'r') as f:
            data = json.load(f)
            data['users'] = fixDictNumericKeys(data['users'])

        # parse issues
        for issue in data['issues']:
            if issue['body']:
                extractAssets(issue['body'], replace)
                issue['body'] = parseBody(replaceAssets(issue['body']))
            else:
                issue['body'] = 'No description provided.'
            issue['user'] = replaceUser(issue['user'], data)
            issue['created_at'] = replaceDateTime(issue['created_at'])
            issue['updated_at'] = replaceDateTime(issue['updated_at'])
            if issue['closed_at']:
                issue['closed_at'] = replaceDateTime(issue['closed_at'])
            if issue['closed_by']:
                issue['closed_by'] = replaceUser(issue['closed_by'], data)
            for comment in issue.get('comments', []):
                extractAssets(comment['body'], replace)
                comment['body'] = parseBody(replaceAssets(comment['body']))
                comment['user'] = replaceUser(comment['user'], data)
                comment['created_at'] = replaceDateTime(comment['created_at'])
                comment['updated_at'] = replaceDateTime(comment['updated_at'])
        
        # write parsed issue data to file
        parsed_file = makepath(ISSUE_PARSED_FILE, replace)
        print(f"Writing parsed issue data to {parsed_file}")
        with open(parsed_file, 'w') as f:
            json.dump(data, f, indent=4)

#################################################################################
# create HTML files from the parsed data
#################################################################################
def createHTML():
    # for each folder in ISSUES_FOLDER, create an index.html file with rendered issues  
    # get list of folders in ISSUES_FOLDER
    if not os.path.exists(ISSUES_FOLDER):
        print(f"Folder {ISSUES_FOLDER} does not exist. Please run download_issues.py first.")
        return

    for repo in REPOS_TO_BACKUP:
        replace = {
            '[repo_name]': repo,
        }
        print(f"Creating HTML for {repo}...")
        data = {'repo_name': repo, 'issues': [], 'users': {}}
        
        # load data from parsed file
        parsed_file = makepath(ISSUE_PARSED_FILE, replace)
        if not os.path.exists(parsed_file):
            print(f"Parsed file {parsed_file} does not exist. Skipping...")
            continue
        with open(parsed_file, 'r') as f:
            data = json.load(f)
            data['users'] = fixDictNumericKeys(data['users'])

        # load template file
        environment = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATES_FOLDER))
        template = environment.get_template(TEMPLATE_FILE)
        # render template with data
        rendered_html = template.render(data=data)
        # write rendered html to file
        print(f"Writing rendered HTML to {ISSUES_FOLDER}/{data['repo_name']}/index.html")
        with open(f"{ISSUES_FOLDER}/{data['repo_name']}/index.html", 'w', encoding="utf-8") as html_file:
            html_file.write(rendered_html)


if __name__ == "__main__":
    # loadRawData()
    # combineRawData()
    parseIssues()
    createHTML()