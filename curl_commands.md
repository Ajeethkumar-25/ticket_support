# Roosterly Helpdesk API - cURL Reference

Collection of ready-to-run cURL commands for all Roosterly Helpdesk endpoints.

---

## Credentials & Variables

```bash
BASE_URL="https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk"
KEY="nrd_round_0d66815246de9ef8d38d058c"
EMAIL="ajkmr2525@gmail.com"
```

---

## 1. Check System Status (`GET /status`)

Returns candidate email, current mode (`practice`), list of endpoints, and counts of `open_tickets` and `handled_tickets`.

```bash
curl -s -X GET "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/status" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com"
```

---

## 2. Get Labelled Reference Examples (`GET /examples`)

Returns the 10 benchmark reference tickets (`E01` to `E10`) with ground-truth labels and reasoning.

```bash
curl -s -X GET "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/examples" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com"
```

---

## 3. List Tickets with Pagination (`GET /tickets`)

### 3a. Open tickets (unhandled)
```bash
curl -s -X GET "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/tickets?status=open&limit=10" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com"
```

### 3b. All tickets (including already handled)
```bash
curl -s -X GET "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/tickets?status=all&limit=10" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com"
```

### 3c. Paginate with Cursor
```bash
curl -s -X GET "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/tickets?status=all&limit=10&cursor=T010" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com"
```

---

## 4. Get a Single Ticket (`GET /tickets/{id}`)

Fetches one ticket by ID, including subject, body, customer plan, and any decision already recorded.

```bash
curl -s -X GET "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/tickets/T001" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com"
```

---

## 5. Reset Practice Tickets (`POST /practice/reset`)

Re-opens all 30 practice tickets so you can run the agent or tests again from scratch.

```bash
curl -s -X POST "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/practice/reset" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com" \
  -H "Content-Type: application/json"
```

---

## 6. Send a Reply to Customer (`POST /tickets/{id}/reply`)

Posts a draft answer in the customer's language.

```bash
curl -s -X POST "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/tickets/T001/reply" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com" \
  -H "Content-Type: application/json" \
  -d "{\"language\":\"nl\",\"category\":\"question\",\"priority\":\"P4\",\"reason\":\"Beantwoord via FAQ F01.\",\"draft_reply\":\"U kunt uw wachtwoord opnieuw instellen via app.roosterly.nl/login met de knop 'Wachtwoord vergeten'.\",\"confidence\":0.95}"
```

---

## 7. Escalate to Human Team (`POST /tickets/{id}/handoff`)

Hands off the ticket to the human support queue with a summary note in English.

```bash
curl -s -X POST "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/tickets/T003/handoff" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com" \
  -H "Content-Type: application/json" \
  -d "{\"language\":\"nl\",\"category\":\"billing\",\"priority\":\"P2\",\"reason\":\"Refund request. Client policy: refunds always escalate to human.\",\"handoff_note\":\"Customer requested refund for closed period. Review billing account.\",\"confidence\":1.0}"
```

---

## 8. Close Spam or Empty Ticket (`POST /tickets/{id}/close`)

Closes the ticket without sending a reply (used for spam or empty messages).

```bash
curl -s -X POST "https://nakywgkztvzkihdjnwbc.supabase.co/functions/v1/helpdesk/tickets/T008/close" \
  -H "Authorization: Bearer nrd_round_0d66815246de9ef8d38d058c" \
  -H "X-Candidate-Email: ajkmr2525@gmail.com" \
  -H "Content-Type: application/json" \
  -d "{\"language\":\"nl\",\"category\":\"other\",\"priority\":\"P4\",\"reason\":\"Crypto promotional spam message.\",\"confidence\":1.0}"
```
