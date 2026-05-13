import os

replacements = {
    "Between Opeyemi and Praise": "Strategy",
    "Praise's Node.js backend": "the Node.js backend",
    "Praise's .env": "the Node.js .env",
    "Praise owns the main Node.js backend which handles": "The main Node.js backend handles",
    "Opeyemi owns this Python FastAPI microservice which handles": "This Python FastAPI microservice handles",
    "(Praise)": "",
    "(Opeyemi)": "",
    "Praise is the orchestrator. He calls": "The Node.js backend is the orchestrator. It calls",
    "he needs AI intelligence, uses the results to make product decisions, and stores the outcomes in PostgreSQL. He does not need to understand the internals of any endpoint — he only": "it needs AI intelligence, uses the results to make product decisions, and stores the outcomes in PostgreSQL. It does not need to understand the internals of any endpoint — it only",
    "Praise needs one environment variable on his Node.js side:": "The Node.js backend needs one environment variable:",
    "gives Praise a quick orientation before he reads": "gives a quick orientation before reading",
    "What Praise Does With It": "Client Action",
    "he needs to act on": "the client needs to act on",
    "How Praise Puts It All Together": "How It All Comes Together",
    "for Praise to read because it shows": "to read because it shows",
    "function Praise calls": "function the Node.js backend calls",
    "What Praise Sends": "Request Payload",
    "Praise builds it": "The client builds it",
    "Praise filters": "The client filters",
    "Praise gets this": "This is obtained",
    "computed by Praise on the Node.js side": "computed on the Node.js side",
    "that Praise already": "that the Node.js backend already",
    "how Praise computes it": "how it is computed",
    "Praise sends one number": "The payload includes one number",
    "Praise multiplies": "The Node.js backend multiplies",
    "Praise must recompute": "The client must recompute",
    "what Praise shows": "what the app shows",
    "Praise should skip": "The client should skip",
    "Praise pre-computed and passed": "pre-computed and passed",
    "Praise recomputes": "The client recomputes",
    "that Praise applies": "that the Node.js backend applies",
    "Praise gets `uploaded_at`": "The Node.js backend gets `uploaded_at`",
    "Praise needs to act on": "the client needs to act on",
    "needed Praise to ensure he always sent": "needed the Node.js backend to ensure it always sent",
    "Praise sends and converts": "the Node.js backend sends and converts",
    "whatever Praise sends": "whatever the Node.js backend sends",
    "What Praise Needs To Do": "What The Client Needs To Do",
    "Praise can send": "The client can send",
    "rely on him implementing": "rely on the Node.js backend implementing",
    "you (Praise) need": "needed",
    "Action for Praise:": "Client Action:"
}

files_to_update = [
    "README.md",
    "to_update.md",
    "docs/api_reference.md"
]

for filepath in files_to_update:
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for old, new in replacements.items():
            content = content.replace(old, new)
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

print("Replacement complete.")
