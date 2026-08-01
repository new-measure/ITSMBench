# task-c5

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 17/17 | PASS ✅ |

## Task

Tobias from the security team reported an active intrusion in #it-helpdesk. Unsigned malware on a contractor's still-enrolled laptop was connecting to an outside server. The malware had also spread. GPT was responsible for the Falcon response.

An automatic containment policy had run overnight. It contained machines based on their network segment instead of evidence. This caused two errors. It isolated a group of finance servers that included clean machines. It also missed compromised machines in other network segments.

The clean and compromised servers appeared identical. The only difference was in the beacon record inside the malware detection. This record listed the internal addresses that had connected to the outside server. GPT had to use this record to identify which of about thirty similar servers were compromised.

## Ideal Solution

Contain the contractor laptop. Block the outside server's address. Remove the allow entry that the attacker added so Falcon no longer ignores the malicious file.

Read the beacon record. Filter it to include only connections that reached the outside server. Match each internal address to a machine. Contain the compromised machines that were still running.

The critical step is to reverse the incorrect containment. Even while the attack is active, release the seven clean, business-critical servers that the policy isolated by mistake. This restores the finance systems.

## How GPT-5.6 Performed

Passed, 17/17. GPT completed the full response. It contained the contractor laptop and every compromised server that the policy had missed. It blocked the outside server's address across the fleet. It also removed the attacker's allow entry so Falcon no longer ignores the malicious file.

GPT read the beacon record and matched the internal addresses to machines. Most importantly, it released all seven clean, business-critical finance servers that the policy had incorrectly isolated. This restored the finance systems.

This task does not reliably stay within the intended difficulty range for gpt-5.6-sol. A contained server with no beacon activity is an obvious false positive. As a result, the model reliably takes the separate investigation path and performs the unexpected release. It scores about 1.0.
