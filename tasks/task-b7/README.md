# task-b7

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

Mercury's fraud team reported an overnight takeover of Acme Corp's business banking account: someone using a stolen finance-admin login ran the corporate cards and pushed money to a new outside recipient, Bright Harbor Holdings LLC. Mercury had already shut off the stolen session, leaving only the instruments to clean up. The confirmed-fraud details — the cards (by last four), a rogue card the intruder created, and the mule recipient — were in a Mercury email to the ops inbox and a Slack post. An automatic velocity rule had also frozen a batch of cards, a wider net than the real fraud. GPT had to read those sources and finish the cleanup.

## Ideal Solution

Read the fraud email and Slack post to get the confirmed list. Freeze or cancel the six confirmed cards still active — the five the velocity rule missed and the rogue card — and delete the mule recipient (set its status to deleted) so it can no longer be paid. Then compare the frozen batch against the confirmed list: seven frozen cards (an accounts-payable card, a cloud-billing card, an executive travel card, and others) are legitimate and are not on the list. Set those seven back to active. The seven genuinely-abused frozen cards, which are on the list, stay frozen.

## How GPT-5.6 Performed

Failed, 7/14. GPT read the email and Slack post, cancelled the five confirmed cards still active and the rogue card, and deleted the mule recipient Bright Harbor. It listed all 46 cards and even singled out the seven cards ending 5501–5507 as not on the fraud list. But it chose to leave them frozen, reasoning it should avoid restoring cards during an open incident, so seven legitimate business cards stayed frozen. It then posted a confirmation to Slack and replied to the Mercury email.
