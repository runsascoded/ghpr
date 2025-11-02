# ghpr shell integration for bash/zsh
# Add to your shell rc: source path/to/ghpr.bash
# Or use: eval "$(ghpr shell-integration bash)"

# Core ghpr aliases for common operations
alias ghpri='ghpr init'                # initialize new PR draft
alias ghpro='ghpr open'                # open existing PR in browser
alias ghprog='ghpr open -g'            # open gist in browser
alias ghprcr='ghpr create'             # create new PR from description
alias ghprcrn='ghpr create -n'         # dry-run: show what PR would be created
alias ghprsh='ghpr show'               # show PR and gist URLs
alias ghprshg='ghpr show -g'           # show only gist URL
alias ghprc='ghpr clone'               # clone existing PR
alias ghprp='ghpr push'                # push to PR (auto-adds footer if gist exists)
alias ghprpn='ghpr push -n'            # dry-run push
alias ghprl='ghpr pull'                # pull from PR (and optionally push back)
alias ghprpg='ghpr push -g'            # push with gist backup (auto-footer)
alias ghprpo='ghpr push -o'            # push and open in browser
alias ghprpF='ghpr push -F'            # push WITHOUT footer
alias ghprd='ghpr diff'                # diff local vs remote PR
alias ghpria='ghpr ingest-attachments' # ingest user-attachments from PR
alias ghpru='ghpr upload'              # upload images to PR's gist
alias ghprs='ghpr sync'                # sync/update PR clones to new naming
alias ghprsn='ghpr sync -n'            # dry-run sync
