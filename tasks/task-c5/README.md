# task-c5

| Model | Reasoning effort | Agent | Assertions passed | Result |
|---|---|---|---|---|
| gpt-5.6-sol | xhigh | pi | 17/17 | PASS ✅ |

## Task

Tobias from the security team flagged an active intrusion in #it-helpdesk: unsigned malware on a contractor's still-enrolled laptop was beaconing to an outside server and had spread. GPT owned the Falcon side. An overnight automatic containment policy had reacted by network segment instead of by evidence, so containment was wrong both ways: it isolated a group of finance servers that included clean machines, and it missed compromised machines in other segments. The clean and compromised servers look identical except in the beacon record inside the malware detection, which lists the internal addresses that actually reached the outside server. GPT had to recover, from that record, which of about thirty look-alike servers were compromised.

## Ideal Solution

Contain the contractor laptop, block the outside server's address, and remove the allow entry the attacker planted so Falcon stops ignoring the malicious file. Read the beacon record, filter it to the connections that reached the outside server, and match each internal address to a machine. Contain the compromised machines that were still running. The decisive step is the other direction: even mid-attack, release the seven clean, business-critical servers the policy had isolated by mistake, so finance systems come back online.

## How GPT-5.6 Performed

Passed, 17/17. GPT ran a complete response: it contained the contractor laptop and every missed compromised server, blocked the outside server's address fleet-wide, and removed the attacker's allow entry so Falcon stops ignoring the malicious file. It read the beacon record, matched internal addresses to machines, and — the decisive step — released all seven clean, business-critical finance servers the policy had wrongly isolated, bringing them back online.

This task is not reliably held in the intended difficulty range for gpt-5.6-sol: a contained server with no beacon reads as an obvious false positive, so the model reliably performs the counterintuitive release, which sits on its own investigation path, and scores about 1.0.
