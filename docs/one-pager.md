# Natural-Language Database Query App: Requirements One-Pager

## Purpose

A web app where business users ask questions of a database in plain English and get back an explanation and the underlying data. Users don't need to know SQL.

The app is configured for a database by supplying a description of that database and its table definitions. v1 supports SQLite only; other database engines are planned for later versions. A sample database is used to build and validate the first version.

## Users

- **Primary:** Business analysts who query data regularly, are comfortable with numbers, and don't write SQL.
- **Secondary:** Support staff, who maintain the configuration files (see Configuration).

## Interaction

- Conversational, like a chatbot.
- Follow-up questions build on the current conversation's context only.
- Switching databases always starts a new conversation.
- Each user has a private history of past interactions, kept indefinitely.
- Users can scroll their history. Search is not required.

## Database Selection

- The app can be configured with multiple databases.
- Before asking questions, the user selects one database.
- Each question runs against that single database. Multi-database questions are out of scope.

## Supported Questions

- **Totals and trends:** e.g. quarter-over-quarter sales.
- **Rankings and top-N:** e.g. the five products with the highest return rate.
- **Filtering to specific records:** e.g. open orders over a threshold for one region.
- **Comparisons across segments:** e.g. churn for new versus existing customers.

## Output

- A plain-English explanation of the answer.
- A table of the underlying results.

## How SQL Is Generated

For every question, the model is given two things about the selected database, and nothing else about it:

1. An overall natural-language **schema description**: what the database is about, how the tables relate, and any business definitions (e.g. "revenue is net of returns").
2. The **table definitions**: every table, its columns, types, keys and relationships.

The full set of table definitions is sent with every question. There is no retrieval, selection or example-matching step.

## Configuration

- Support maintains one configuration file per database, covering:
  - Database connection
  - The schema description (free text)
  - The table definitions (tables, columns, types, keys, relationships)
- Files load at app startup. Changes take effect on restart.
- At startup, the app checks that each configured database connects, and that the configured tables and columns exist in it.

## Development Inputs

To build and validate the first version, the following are provided:

- A **sample database**, with its schema description and table definitions in the configuration format above.
- A **validation dataset**: natural-language questions paired with the SQL that correctly answers each one, used to check that the app generates correct queries.

The sample database is the initial test case only. Nothing in the app may be specific to it.

## Access Control

- None for v1. Every user can see every configured database.

## Must Never Happen

- Any change to or deletion of data. The app is read-only.
- A wrong answer given silently. Ambiguous questions or incomplete data must be flagged to the user.

## Out of Scope (v1)

- Multi-database questions
- Scheduled reports and alerts
- Writing data back to any database
- Forecasting and predictions
- Access control by role, team, or region
- Searching user history
