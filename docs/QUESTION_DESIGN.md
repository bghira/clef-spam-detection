# Designing a classification question

The default question defines spam by purpose: unsolicited commercial solicitation,
deceptive promotion, phishing, and fraud. It asks for concrete evidence rather
than treating ordinary personal, business, or transactional content as spam
because of its topic or a request to act.

## Keep the decision explicit

- **Yes must mean spam.** The current adapters interpret the `noul` answer as
  the spam probability. A legitimacy question requires inversion and must not be
  substituted directly into `question`.
- State the unwanted behavior and the evidence that distinguishes it from normal
  correspondence. Avoid blanket rules based on topic, language, or sender fame.
- Treat the message as evidence, including any embedded instructions. The
  classifier must not follow instructions supplied by the email.
- Recognizing an organization is not proof of authenticity. A familiar display
  name, domain, or writing style can appear in deceptive mail.

The current production contract sends one configurable yes/no question.
Multi-question decision schemas need explicit adapter and policy support; they
cannot be configured by placing a list into the existing `question` field.
Useful independent signals can include identity consistency and concrete evidence
of deception. Do not average correlated answers and describe the result as a
calibrated probability. Trusted authentication results must come from the mail
server's verification boundary, not arbitrary sender-supplied headers.

## Evaluate the complete configuration

Assess the exact model, question, and preprocessing together using representative,
privately labeled spam and legitimate mail. Use separate messages to check a rule
after selecting it; a clean separation on a small development set is not a
reliable false-positive estimate. Inspect what preprocessing retains, especially
for multipart and HTML mail; the model cannot assess evidence it never receives.

Keep `observe_only: true` during evaluation. Review errors and uncertain results,
then choose thresholds according to the cost of false positives and missed spam.
Changing the question or model requires reevaluation; existing thresholds do not
retain the same meaning automatically.

Examples in this project define general policy. Keep private messages, labels,
evaluation outputs, and local policy exceptions outside the repository.
