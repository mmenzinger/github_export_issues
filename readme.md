# Github Issue Downloader #

## Description ##
This is a simple tool to download all issues of a repo (including attached images) as json and as a simpe html page for local view.

## Usage ##
Create a *fine-grained token* with *read* access to *issues*, *pull requests* and *metadata*.

Log into github in your browser and get the user_session cookie from developer tools > cookies > user_session
(This is currently needed to download assets like images, see https://stackoverflow.com/questions/76666026/download-github-pull-request-description-images-remotely-or-via-the-api)

Create the file ```settings.py``` and store both and a list of repos in it.
```
API_TOKEN = "github_..." # fine-grained token

# !!! this expires regularly, so you need to update it !!!
# (login to github -> dev tools -> cookies -> user_session)
SESSION_COOKIE = "..."

REPOS_TO_BACKUP = [
    "my_repo_1",
    ...
]
```

Run backup_issues.py and wait for it to finish. You can find the result in the issues folder. Run again to update for new issues, to manually re download old ones just delete the cache.