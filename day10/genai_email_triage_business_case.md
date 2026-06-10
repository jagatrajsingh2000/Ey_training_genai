# GenAI Business Case: Multilingual Email Triage

## Problem Statement

A customer support team receives a very large number of emails every day in different languages. Each email needs to be read, understood, classified, prioritized, and sent to the correct team.

At the moment, this work is mostly done manually. This takes a lot of time and depends heavily on human agents. A GenAI-based solution can help by reading the email, identifying the issue, and suggesting the right team for routing.

## 1. Business Impact

### Current Situation

- Around 8,000 emails are received every day.
- Each email takes about 7 minutes to triage manually.
- Agents spend a lot of time reading and routing emails.
- Response time can be slow during high-volume periods.

### Expected Improvement

- Reduce triage time by 60% to 70%.
- Save more than £300K per year.
- Reduce response time from hours to minutes.
- Improve routing accuracy by around 20%.

### Business Value

This solution can reduce operational cost and improve customer experience. It also makes the support process more scalable because the company can handle more emails without adding the same number of extra agents.

## 2. Data Requirements

### Data Needed

The system will need historical customer emails and their past labels.

Useful labels include:

- Email category, such as fraud, account issue, card issue, loan query, or complaint
- Priority level
- Correct routing team
- Language of the email

### Data Volume

Around 50,000 to 100,000 historical emails would be useful for testing, evaluation, and improvement of the solution.

### Privacy Requirements

Customer emails may contain personal information, so the data must be handled carefully.

Important privacy steps:

- Mask personal details such as customer name, account number, phone number, and email address.
- Do not store raw customer emails in application logs.
- Follow GDPR and internal data protection rules.
- Keep access limited to approved users and systems.

### Use of Synthetic Data

Synthetic data can be used for testing and edge cases. For example, we can create sample emails in different languages or unusual customer scenarios.

Possible tools:

- GPT-4o
- CTGAN

Synthetic data should support real data, not completely replace it.

## 3. Model Selection

### Recommended Model

**Claude 3.5 Sonnet**

### Alternative Model

**GPT-4o**

### Why Claude 3.5 Sonnet?

Claude 3.5 Sonnet is a good choice because it understands multiple languages well and can produce structured outputs such as JSON. This is useful when the system needs to return fields like category, priority, language, confidence score, and routing team.

### Why GPT-4o?

GPT-4o is also a strong option. It is fast and suitable for real-time use cases where emails need to be processed quickly.

### Cost Optimization

For high-volume emails, a smaller model such as GPT-4o-mini can be used for simple cases. More complex or low-confidence cases can be sent to a stronger model.

## 4. Risks and Mitigation

### Hallucination Risk

The model may classify an email incorrectly or route it to the wrong team.

Mitigation:

- Use structured JSON output.
- Add confidence scores.
- Send low-confidence cases to human review.
- Test the model regularly against real examples.

### Bias Risk

The model may perform better for some languages or writing styles than others.

Mitigation:

- Test the system on multilingual data.
- Include different writing styles and regions in evaluation.
- Monitor accuracy by language and customer segment.

### Privacy Risk

Emails may contain sensitive personal information. If not handled correctly, this can create GDPR and compliance issues.

Mitigation:

- Mask or tokenize personal data.
- Avoid raw email storage in logs.
- Use secure cloud deployment such as Azure OpenAI or a private VPC.
- Apply access controls and audit logs.

### Vendor Lock-In Risk

The company may become too dependent on one LLM provider.

Mitigation:

- Use an abstraction layer or API gateway.
- Support more than one model provider.
- Keep prompts, evaluation data, and routing logic portable.

## 5. Success Metrics for 90 Days

### Main KPI

**Email classification accuracy should be at least 92%.**

This should be checked through human evaluation.

### Other KPIs

- Triage time reduction should be at least 60%.
- Auto-routing rate should be at least 70%.
- Manual re-routing should reduce by at least 30%.
- Average response time should improve.

## Final Summary

This solution uses GenAI to read and classify multilingual customer emails automatically. It can reduce manual triage effort, improve routing speed, and help customers get faster responses. Sensitive data must be protected through masking, secure deployment, and human review for uncertain cases.
