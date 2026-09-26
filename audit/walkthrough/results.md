| Task | Repository @ version | Query | Expected | Rank | Verdict | Sources match version | Latency |
|---|---|---|---|---:|---|---|---:|
| T2-demo | demo @ working-tree | Where is openBluetoothSettings used? | bluetooth/BluetoothAgent.js::BluetoothAgent.execute | 2 | PASS | True | 160 ms |
| T3 | demo @ working-tree | Which functions call checkBluetoothPermission before openBluetoothSett | bluetooth/BluetoothAgent.js::BluetoothAgent.execute | 3 | PASS | True | 145 ms |
| T6-demo | demo @ working-tree | qxzjvnonexistentidentifier | (none) | — | PASS | True | 125 ms |
| T4-demo-v1 | demo @ v1 | Where is the saved session restored after restart? | auth/AuthService.js::AuthService.restore | 3 | PARTIAL | True | 130 ms |
| T4-demo-v2 | demo @ v2 | Where is the saved session restored after restart? | session/SessionManager.js::SessionManager.restore | 3 | PARTIAL | True | 143 ms |
| T1 | expressjs/express @ 4.21.2 | Which code picks the response format based on what the client says it  | lib/response.js::format | 2 | PARTIAL | True | 234 ms |
| T2 | expressjs/express @ 4.21.2 | Where is compileQueryParser used? | lib/application.js::set | 2 | PASS | True | 305 ms |
| T4-4.18.2 | expressjs/express @ 4.18.2 | where is the redirect location URL encoded | lib/response.js::location | 1 | PASS | True | 118 ms |
| T4-4.19.2 | expressjs/express @ 4.19.2 | where is the redirect location URL encoded | lib/response.js::location | 1 | PASS | True | 280 ms |
| T4-4.21.2 | expressjs/express @ 4.21.2 | where is the redirect location URL encoded | lib/response.js::location | 1 | PASS | True | 270 ms |
| T5 | expressjs/express @ 4.21.2 | Where is view template rendering implemented? | lib/view.js::render, lib/application.js::render, lib/response.js::render, lib/application.js::tryRender | 9 | FAIL | True | 308 ms |
| T6 | expressjs/express @ 4.21.2 | Where is the Kafka consumer offset committed? | (none) | — | PASS | True | 338 ms |
