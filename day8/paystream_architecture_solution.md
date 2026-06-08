# PayStream Architecture Solution

## Problem Statement
SCENARIO BACKGROUND

PayStream is a B2B payment processor handling 4 million transactions per day for 600 merchant clients. Their platform must guarantee every payment is settled exactly once, notify downstream systems about account activity, and produce a real-time fraud risk score before authorisation completes.

The engineering team is designing the messaging layer. They need to choose the right pattern for each integration below.

## Complete Architecture Diagram

```text
                        ┌─────────────────┐
                        │   Merchant API  │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   API Gateway   │
                        └────────┬────────┘
                                 │
                                 ▼
              ┌─────────────────────────────────────┐
              │            Payment Core             │
              │   Validation, Auth, Orchestration   │
              └─────────┬─────────────────┬─────────┘
                        │                 │
                        │ D               │ A
                        │ Fraud Request   │ Settlement Command
                        ▼                 ▼

                ┌──────────────┐   ┌──────────────┐
                │ Fraud Queue  │   │ Settlement Q │
                └──────┬───────┘   └──────┬───────┘
                       │                  │
                       ▼                  ▼
                ┌──────────────┐   ┌──────────────┐
                │ Fraud Engine │   │Ledger Service│
                └──────────────┘   └──────┬───────┘
                                          │
                                          │ Payment Settled Event
                                          ▼
                                ┌──────────────────┐
                                │    Event Bus     │
                                │  (Pub/Sub Topic) │
                                └────┬─────┬────┬──┘
                                     │     │    │
                                     │ B   │ B  │ B
                                     ▼     ▼    ▼

                       ┌──────────┐ ┌──────────────┐ ┌──────────┐
                       │Analytics │ │ Notification │ │ Fraud    │
                       │Pipeline  │ │ Hub          │ │ Profile  │
                       └──────────┘ └──────┬───────┘ └──────────┘
                                           │
                                           │ C
                                           ▼
                                    ┌──────────────┐
                                    │ Notify Queue │
                                    └──────┬───────┘
                                           │
                         ┌─────────────────┼─────────────────┐
                         ▼                 ▼                 ▼
                   ┌──────────┐      ┌──────────┐      ┌──────────┐
                   │ Worker 1 │      │ Worker 2 │      │ Worker 3 │
                   └──────────┘      └──────────┘      └──────────┘

────────────────────────────────────────────

Account Updates

 KYC Updated / Account Suspended
                │
                ▼
         ┌────────────┐
         │ Event Bus  │
         └─────┬──────┘
               │
      ┌────────┼─────────┐
      ▼        ▼         ▼
 Payment   Merchant   Compliance
  Core      Portal     Service

────────────────────────────────────────────

Midnight Reconciliation

 600 Files
      │
      ▼
   Queue
      │
 ┌────┼────┐
 ▼    ▼    ▼
W1   W2   W3
```

## Question to Answer Mapping

| ID | Scenario | Answer | Why |
|---|---|---|---|
| A | Settlement Command | **Queue** | Exactly-once processing, single consumer, retries |
| B | Payment Received Broadcast | **Event Bus** | Multiple services react independently |
| C | SMS/Push Notifications | **Queue** | One worker per message, load balancing |
| D | Fraud Score Request | **Queue** | Request-reply, one consumer |
| E | Account State Change Events | **Event Bus** | Publish state changes to many services |
| F | End-of-Day Reconciliation | **Queue** | Distribute files across worker pool |

## Solution Explanation

### A. Settlement Command

Settlement is a task that must be processed carefully by one service. The same settlement should not be processed by multiple consumers at the same time. A **Queue** is the best choice because it supports retries, controlled processing, and one worker handling each message.

### B. Payment Received Broadcast

When a payment is received or settled, many services may need to know about it. Notification, analytics, and fraud profile services can all react independently. An **Event Bus** is the best choice because it supports publish-subscribe and fan-out.

### C. SMS and Push Notifications

Sending notifications is work that needs to be distributed across workers. Each notification should be sent once by one worker. A **Queue** is suitable because it provides load balancing and retry support.

### D. Fraud Score Request

Fraud scoring is a request that should be handled by the fraud engine. The payment system asks for a score and expects one result. A **Queue** works well because it sends the request to one consumer.

### E. Account State Change Events

When KYC is updated or an account is suspended, many services should be informed. Payment Core, Merchant Portal, and Compliance Service may all need the same event. An **Event Bus** is the correct choice because it broadcasts state changes to multiple subscribers.

### F. End-of-Day Reconciliation

At midnight, hundreds of files need processing. This is a workload that can be split across multiple workers. A **Queue** is the best choice because it distributes jobs among workers and supports retry if a file fails.

## Decision Rule

### Use Queue When

```text
"Do this work"
```

Examples:

- Settlement command
- Fraud request
- SMS sending
- Reconciliation jobs

Characteristics:

- One consumer handles each message
- Retry support
- Load balancing
- Exactly-once or at-least-once processing
- Good for commands and background jobs

## Use Event Bus When

```text
"This happened"
```

Examples:

- Payment received
- Account updated
- User registered
- Order shipped

Characteristics:

- Multiple consumers can react
- Publish/subscribe pattern
- Fan-out support
- Future subscribers can be added easily
- Good for events and state changes

## Final Answers

```text
A → Queue
B → Event Bus
C → Queue
D → Queue
E → Event Bus
F → Queue
```

## Interview Explanation

If the sender wants someone to perform a task, use a **Queue**.

If the sender wants to announce that something happened and multiple services may react, use an **Event Bus**.
