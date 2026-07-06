# Review principles — why the sweep and the recheck are shaped the way they are

Three transferable ideas underlie the second-read sweep (b3b) and the recheck (b4–b6). They are
borrowed from independent multi-pass code review and stated generally, so they apply to any
package. Skeletons point here; this file is not pasted into worker contexts.

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

**How defects cluster.** These principles rest on one empirical regularity: defects are not
independently distributed across files. A file the author was careless in once is more likely to
carry a second, unrelated defect than a file with no findings at all. That is why the second-read
trigger keys on *any* confirmed finding in a file (not only severe ones) and re-reads the whole
file, not just the neighbourhood of the first finding.
