# Github Issue Downloader #

## Usage ##
Create a *fine-grained token* with *read* access to *issues*, *pull requests* and *metadata*.

Log into github in your browser and get the user_session cookie from developer tools > cookies > user_session
(This is currently needed to download assets like images, see https://stackoverflow.com/questions/76666026/download-github-pull-request-description-images-remotely-or-via-the-api)

Store both and a list of repos in the file ```settings.py```.
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
