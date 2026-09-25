# 04 — Evidence Adapters and Fixture Contracts

## Design goal

SiloBreaker should not couple inference logic directly to GitHub, Slack or Jira schemas. Each connector maps source-specific payloads into one canonical `EvidenceItem` contract.

For the hackathon, adapters may read fixture JSON instead of calling live services. The fixtures should resemble real provider payloads closely enough that replacing the fixture client with a read-only HTTP client does not change downstream analysis.

## Canonical normalized contract

```json
{
  "id": "github:pr-review:80",
  "source": "github",
  "source_type": "pull_request_review",
  "external_id": "80",
  "parent_external_id": "pr:12",
  "author": {
    "id": "octocat",
    "display_name": "octocat"
  },
  "participants": ["octocat"],
  "timestamp": "2019-11-17T17:43:43Z",
  "title": "Review on PR #12",
  "body": "Here is the body for the review.",
  "url": "https://github.com/octocat/Hello-World/pull/12#pullrequestreview-80",
  "metadata": {
    "state": "APPROVED",
    "commit_id": "..."
  }
}
```

### Rules

- Preserve source identity and parent relationships.
- Keep raw source metadata in `metadata`/JSONB, but lift commonly queried fields into normalized columns.
- Do not add inferred topic, risk, target gap, expected question or correct answer.
- Store original provider payload separately for debugging if desired, but model input should use a bounded normalized projection.
- One incident represented in several tools can still be one underlying operational event after event linking.

---

## GitHub adapter

### Source operations

Useful read-only REST resources include:

- pull requests;
- changed files;
- reviews;
- inline review comments;
- general PR discussion/comments.

For D-Day, use local JSON fixtures first. A live adapter is stretch work.

### Reduced mock provider response

Based on GitHub's official pull-request review response shape:

```json
{
  "id": 80,
  "user": {
    "login": "octocat",
    "id": 1
  },
  "body": "Here is the body for the review.",
  "state": "APPROVED",
  "html_url": "https://github.com/octocat/Hello-World/pull/12#pullrequestreview-80",
  "pull_request_url": "https://api.github.com/repos/octocat/Hello-World/pulls/12",
  "submitted_at": "2019-11-17T17:43:43Z",
  "commit_id": "ecdd80bb57125d7ba9641ffaa4d7d2c19d3f3091",
  "author_association": "COLLABORATOR"
}
```

### Mapping

| Provider field | Canonical field |
|---|---|
| `id` | `external_id` |
| `user.login` | `author.id/display_name` |
| `submitted_at` | `timestamp` |
| `body` | `body` |
| `html_url` | `url` |
| `state`, `commit_id`, `author_association` | `metadata` |
| PR number/path | `parent_external_id` |

Official references:

- Pull request reviews: https://docs.github.com/en/rest/pulls/reviews
- Pull requests: https://docs.github.com/en/rest/pulls/pulls
- Pull request comments: https://docs.github.com/en/rest/pulls/comments
- Issue/PR conversation comments: https://docs.github.com/en/rest/issues/comments

---

## Slack adapter

### Source operation

`conversations.history` returns message events for a channel/conversation. Thread replies can be fetched separately with `conversations.replies` if the MVP needs thread context.

### Reduced mock provider response

Based on Slack's official typical success response:

```json
{
  "ok": true,
  "messages": [
    {
      "type": "message",
      "user": "U123ABC456",
      "text": "Settlement remains pending after provider acceptance; check the existing transaction before retrying.",
      "ts": "1512085950.000216"
    },
    {
      "type": "message",
      "user": "U222BBB222",
      "text": "I will add this exception to the follow-up ticket.",
      "ts": "1512104434.000490"
    }
  ],
  "has_more": false,
  "response_metadata": {
    "next_cursor": ""
  }
}
```

### Mapping

| Provider field | Canonical field |
|---|---|
| channel ID + `ts` | `external_id` |
| `user` | `author.id` |
| `text` | `body` |
| Slack `ts` converted to UTC | `timestamp` |
| channel/thread timestamp | `parent_external_id` / metadata |
| permalink from `chat.getPermalink` when available | `url` |

Slack messages are variable: attachments, blocks, bot messages and subtype events may have different fields. The adapter must explicitly choose which message types become evidence.

Official references:

- `conversations.history`: https://docs.slack.dev/reference/methods/conversations.history/
- `conversations.replies`: https://docs.slack.dev/reference/methods/conversations.replies/
- `chat.getPermalink`: https://docs.slack.dev/reference/methods/chat.getPermalink/

---

## Jira Cloud adapter

### Source operations

For a knowledge-risk corpus, useful read-only data includes:

- issue details;
- selected fields such as summary, description, assignee, reporter, status and labels;
- comments;
- changelog when lifecycle context matters.

Jira multiline text fields use Atlassian Document Format (ADF), so the adapter should convert supported ADF nodes to bounded plain text/Markdown before downstream analysis.

### Reduced mock provider response

The exact `IssueBean` is large and tenant/custom-field dependent. The mock should retain only fields used by SiloBreaker:

```json
{
  "id": "10001",
  "key": "PAY-321",
  "self": "https://example.atlassian.net/rest/api/3/issue/10001",
  "fields": {
    "summary": "Settlement pending after provider acceptance",
    "status": {
      "name": "Done"
    },
    "assignee": {
      "accountId": "alice-account",
      "displayName": "Alice"
    },
    "reporter": {
      "accountId": "bob-account",
      "displayName": "Bob"
    },
    "created": "2026-08-18T10:30:00.000+0000",
    "updated": "2026-08-18T12:05:00.000+0000",
    "description": {
      "type": "doc",
      "version": 1,
      "content": [
        {
          "type": "paragraph",
          "content": [
            {
              "type": "text",
              "text": "Recovery required checking the existing provider transaction before any retry."
            }
          ]
        }
      ]
    }
  }
}
```

### Mapping

| Provider field | Canonical field |
|---|---|
| `key` | `external_id` |
| `fields.reporter` / selected semantic actor | `author` or metadata |
| `fields.assignee`, reporter, commenters | `participants` |
| `fields.created/updated` | `timestamp` + metadata |
| `fields.summary` | `title` |
| ADF description/comments | normalized `body` |
| issue browse URL | `url` |
| status/labels/priority/etc. | `metadata` |

Official references:

- Jira Cloud REST v3 Issues: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/
- Jira Cloud REST v3 issue fields: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-fields/
- Atlassian Document Format: https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/

---

## Document/runbook adapter

A generic document adapter is useful for Markdown/text runbooks in the fixture corpus:

```json
{
  "id": "doc:settlement-runbook",
  "source": "document",
  "source_type": "runbook",
  "external_id": "settlement-runbook.md",
  "author": null,
  "participants": [],
  "timestamp": "2026-08-01T00:00:00Z",
  "title": "Settlement Runbook",
  "body": "Diagnosis steps ...",
  "url": null,
  "metadata": {
    "path": "runbooks/settlement.md"
  }
}
```

## Fixture repository structure

```text
fixtures/
  input/
    manifest.json
    github/
      pr_1842.json
      review_80.json
    slack/
      settlement_thread.json
    jira/
      PAY-321.json
    docs/
      settlement_runbook.json
  oracle/
    expected_findings.json
    expert_capture.json
    successor_answers.json
```

**Critical isolation rule:** `fixtures/oracle` is used by tests/evaluation only and must never be included in inference payloads or frontend assets.

## Adapter interface

```python
class EvidenceAdapter(Protocol):
    source: str

    def load(self, request: AdapterRequest) -> list[ProviderRecord]: ...
    def normalize(self, record: ProviderRecord) -> EvidenceItemInput: ...
```

The fixture adapter and a future live adapter must emit the same `EvidenceItemInput`.
