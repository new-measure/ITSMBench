# task-b7

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 7/14 | FAIL ❌ |

## Task

Mercury's fraud team reported that someone took over Acme Corp's business banking account overnight. The person used a stolen finance-admin login. They used the corporate cards and sent money to a new external recipient named Bright Harbor Holdings LLC. Mercury had already disabled the stolen session. Only the payment instruments still needed cleanup.

A Mercury email to the ops inbox and a Slack post contained the confirmed fraud details. These details included the cards by their last four digits, a fraudulent card created by the intruder, and the recipient used to receive the stolen money. An automatic velocity rule had also frozen a group of cards. This group included more cards than those involved in the confirmed fraud. GPT had to read the email and Slack post and complete the cleanup.

## Ideal Solution

Read the fraud email and Slack post to find the confirmed list. Freeze or cancel the six confirmed cards that are still active. These are the five cards missed by the velocity rule and the fraudulent card created by the intruder. Delete the recipient Bright Harbor Holdings LLC by setting its status to deleted. This prevents anyone from sending more payments to it.

Next, compare the frozen cards with the confirmed list. Seven frozen cards are legitimate and are not on the confirmed list. They include an accounts-payable card, a cloud-billing card, an executive travel card, and other cards. Set these seven cards back to active. The seven frozen cards that were genuinely abused are on the confirmed list. Keep those seven cards frozen.

## How GPT-5.6 Performed

Failed, 7/14. GPT read the email and Slack post. It cancelled the five confirmed cards that were still active and the fraudulent card created by the intruder. It also deleted the recipient Bright Harbor Holdings LLC. It listed all 46 cards and identified the seven cards ending in 5501–5507 as not being on the fraud list.

However, GPT left those seven cards frozen. It reasoned that it should not restore cards while the incident was still open. As a result, seven legitimate business cards remained frozen. GPT then posted a confirmation in Slack and replied to the Mercury email.
