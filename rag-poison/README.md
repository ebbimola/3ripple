RAG Poisoning & Infrastructure Hardening

This lab is a companion to the blog post "Securing the AI Highway: Protecting Your Infrastructure" It demonstrates how an attacker can perform a **Semantic Override** on an enterprise RAG system.

## The Scenario
Our HR Assistant bot is designed to help employees with policy questions. However, the system is configured to index "Incoming Feedback" automatically. An attacker sends a feedback form containing a "System Update" instructions.

## The Vulnerability
Because the RAG system looks for **Semantic Similarity**, the attacker's use of urgent keywords ("URGENT", "PAYROLL", "UPDATE") gives their malicious text a higher score than the legitimate, static policy.

## How to Run
1. Install dependencies: `pip install -r requirements.txt`
2. Run the vulnerable simulation: `python src/app.py`
3. Observe how the "Attacker Site" info is retrieved.
4. Run the secure version: `python src/secure_app.py`

## Enterprise Hardening Checklist
- [ ] Implement Metadata Filtering (Namespace separation).
- [ ] Sanitize inputs for "Direct Instructions" (e.g., "Ignore previous instructions").
- [ ] Enable LLM Observability to flag atypical context retrieval.
