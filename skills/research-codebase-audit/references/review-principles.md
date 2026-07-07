# Review principles — why the sweep and the recheck are shaped the way they are

Four transferable ideas underlie the first-pass read (b2), the second-read sweep (b3b), and the
recheck (b4–b6). They are borrowed from independent multi-pass code review and stated generally,
so they apply to any package. Skeletons point here; this file is not pasted into worker contexts.

1. **Several independent passes with distinct mandates beat one open-ended pass.** A single
   reader told to "find everything" satisfices — it stops at the first defect in a file and
   moves on. Two readers, each with a *narrow, different* mandate ("first pass: find any
   defect"; "second pass: assume the first reader missed one, find it") cover more than one
   reader given twice the time. The second-read sweep is exactly this: a fresh-context pass over
   an already-flagged file whose only job is what the first reader missed. At `deep` depth the
   sweep itself runs a second pass with yet another lens.

2. **Independent per-finding validation beats batched validation.** Rechecking findings one at a
   time, each by a reader who weighs the evidence for and against that finding on its own,
   catches more false positives than a single reader skimming a batch. The recheck stage is
   per-cluster by default and per-finding at `deep` depth (the depth-knob table in SKILL.md).

3. **Confidence gating keeps precision while thoroughness rises.** Adding reading passes raises
   recall but also raises false positives. The defence is not fewer passes — it is that every
   new row from a later pass enters as an *unverified candidate* and must survive the recheck
   before it can become a confirmed finding. Thoroughness is spent on discovery; precision is
   enforced downstream. This is why second-read rows never enter as `confirmed`.

4. **Establishing behavior beats inferring it.** When a fragment of code's actual behavior is
   not self-evident, running a small, faithful, worker-retyped reproduction of it on a synthetic
   input settles in one observation what reading can only estimate. Reading is exactly where
   such defects hide: a comment stating what a guard or an in-loop flag does primes the reader
   past the very condition that is wrong — the reader verifies the comment's story, not the
   code's behavior. For the same reason the trigger for probing is structural, not felt: a
   comment or docstring that asserts a fragment's behavior makes the fragment non-self-evident
   by definition (the comment is a claim to verify, never evidence of behavior), because the
   comment that primes a reader past the wrong condition also primes them past any
   "probe when uncertain" trigger — a subjective trigger never fires on exactly the defects
   that motivate probing. The audit therefore uses its synthetic-test capability for discovery,
   not only defence: the recheck long ran retyped synthetic tests to refute existing suspicions,
   and the Empirical verification rule (`registers.md`) extends the same probe to
   comment-asserted fragments at any review-ladder level where the review mode allows a probe
   within budget — with faithful isolation and untrusted-content guardrails, because a badly
   isolated fragment giving false reassurance is worse than not probing.

**How defects cluster.** These principles rest on one empirical regularity: defects are not
independently distributed across files. A file the author was careless in once is more likely to
carry a second, unrelated defect than a file with no findings at all. That is why the second-read
trigger keys on *any* confirmed finding in a file (not only severe ones) and re-reads the whole
file, not just the neighbourhood of the first finding.
