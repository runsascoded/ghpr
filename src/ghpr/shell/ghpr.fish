# ghpr shell integration for fish
# Add to your config.fish: source path/to/ghpr.fish
# Or use: ghpr shell-integration fish | source

# Core ghpr aliases for common operations
function ghpri                         # initialize new PR draft and cd to gh/new
    ghpr init $argv && cd gh/new
end
alias ghpro='ghpr open'                # open existing PR in browser
alias ghprog='ghpr open -g'            # open gist in browser
alias ghprcr='ghpr create'             # create new PR from description
alias ghprcrn='ghpr create -n'         # dry-run: show what PR would be created
alias ghprsh='ghpr show'               # show PR and gist URLs
alias ghprshg='ghpr show -g'           # show only gist URL
function ghprc                         # clone PR and cd into directory
    set dir (ghpr clone $argv)
    if test $status -eq 0 -a -n "$dir"
        cd $dir
    end
end
alias ghprp='ghpr push'                # push to PR (auto-adds footer if gist exists)
alias ghprpn='ghpr push -n'            # dry-run push
alias ghprl='ghpr pull'                # pull from PR (and optionally push back)
alias ghprpg='ghpr push -g'            # push with gist backup (auto-footer)
alias ghprpo='ghpr push -o'            # push and open in browser
alias ghprpF='ghpr push -F'            # push WITHOUT footer
alias ghprd='ghpr diff'                # diff local vs remote PR
alias ghpria='ghpr ingest-attachments' # ingest user-attachments from PR
alias ghpru='ghpr upload'              # upload images to PR's gist
