import os
import re

def main():
    readme_path = 'README.md'
    if not os.path.exists(readme_path):
        print(f"Error: {readme_path} not found.")
        return

    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()

    main_regex = r'(.*?)\n---\n\n---\n\n# `/score` Endpoint'
    score_regex = r'# `/score` Endpoint\n(.*?)---\n\n---\n\n# `/fraud-check` Endpoint'
    fraud_regex = r'# `/fraud-check` Endpoint\n(.*?)---\n\n---\n\n# `/match` and `/match/feedback` Endpoints'
    match_regex = r'# `/match` and `/match/feedback` Endpoints\n(.*)'

    main_match = re.search(main_regex, content, re.DOTALL)
    score_match = re.search(score_regex, content, re.DOTALL)
    fraud_match = re.search(fraud_regex, content, re.DOTALL)
    match_match = re.search(match_regex, content, re.DOTALL)

    if not all([main_match, score_match, fraud_match, match_match]):
        print('Failed to match all sections. The README.md format may have changed.')
        return

    os.makedirs('docs', exist_ok=True)
    
    with open('docs/scoring.md', 'w', encoding='utf-8') as f:
        f.write('# `/score` Endpoint\n' + score_match.group(1).strip() + '\n')
        
    with open('docs/fraud_check.md', 'w', encoding='utf-8') as f:
        f.write('# `/fraud-check` Endpoint\n' + fraud_match.group(1).strip() + '\n')
        
    with open('docs/matching.md', 'w', encoding='utf-8') as f:
        f.write('# `/match` and `/match/feedback` Endpoints\n' + match_match.group(1).strip() + '\n')

    new_readme = main_match.group(1).strip() + '''

---

## Detailed Documentation

The technical documentation for the ML endpoints has been split into dedicated files for readability. Please refer to the following guides:

- **[Scoring System Documentation](docs/scoring.md)**: Deep dive into the `/score` endpoint, the four signals, and why it's rule-based.
- **[Fraud Detection Documentation](docs/fraud_check.md)**: Deep dive into the `/fraud-check` endpoint, Isolation Forest, River Online Learning persistence, and timestamp integrity.
- **[WorkConnect Matching Documentation](docs/matching.md)**: Details on the `/match` and `/match/feedback` endpoints, including the rule-based to ML transition.
'''
    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(new_readme)

    print('Successfully split documentation into docs/ directory and updated README.md.')

if __name__ == '__main__':
    main()
