| | Before | After |
|---|---|---|
| States × viewports crawled | 21 | 21 |
| Visible controls inventoried (sum over states) | 1148 | 1094 |
| Unique control interactions exercised | 340 | 326 |
| outcome `CHANGED` | 249 | 312 |
| outcome `DISABLED` | 3 | 3 |
| outcome `ERROR` | 41 | 9 |
| outcome `NOT_FOUND_ON_RELOAD` | 44 | 0 |
| outcome `NO_VISIBLE_CHANGE` | 2 | 2 |
| outcome `STATE_SETUP_FAILED` | 1 | 0 |
| interactions with console/page errors | 10 | 0 |
| interactions with failed network requests | 0 | 0 |
| axe critical (rule × state, Monaco excluded) | 21 | 0 |
| axe serious (rule × state, Monaco excluded) | 17 | 0 |
| axe moderate (rule × state, Monaco excluded) | 24 | 5 |
| states with horizontal overflow | 0 | 0 |

Covered controls in the final crawl (element at the control's centre): {'DIV': 5, 'SPAN': 1, 'companion': 3}

Source aria-labels never seen at runtime: ['Code companion', 'Dismiss error', 'Open source files', 'Repository files', 'Source comparison', 'Source viewer', 'Source-backed call graph', 'Workspace tools', 'Workspace views']

Final-crawl rows that are not CHANGED:
- desktop / code (initial) / link "ASTFLOW home" → NO_VISIBLE_CHANGE
- desktop / code (initial) / textbox "" → ERROR (elementHandle.fill: Timeout 10000ms exceeded.) covered by DIV
- desktop / code (initial) / button "Send question" → DISABLED
- desktop / compare (after run) / textbox "" → ERROR (elementHandle.fill: Timeout 10000ms exceeded.) covered by SPAN
- tablet / code (initial) / textbox "" → ERROR (elementHandle.fill: Timeout 10000ms exceeded.) covered by DIV
- tablet / code after search / button "Close settings/deeplinks.js" → ERROR (elementHandle.click: Timeout 5000ms exceeded.) covered by companion
- tablet / code after search / button "Send question" → DISABLED
- tablet / compare (after run) / textbox "" → ERROR (elementHandle.fill: Timeout 10000ms exceeded.) covered by DIV
- mobile / code (initial) / link "ASTFLOW home" → NO_VISIBLE_CHANGE
- mobile / code (initial) / textbox "" → ERROR (elementHandle.fill: Timeout 10000ms exceeded.) covered by DIV
- mobile / code after search / button "JSdeeplinks.js" → ERROR (elementHandle.click: Timeout 5000ms exceeded.) covered by companion
- mobile / code after search / button "Close settings/deeplinks.js" → ERROR (elementHandle.click: Timeout 5000ms exceeded.) covered by companion
- mobile / code after search / button "Send question" → DISABLED
- mobile / compare (after run) / textbox "" → ERROR (elementHandle.fill: Timeout 10000ms exceeded.) covered by DIV
