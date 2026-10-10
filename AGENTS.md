# Working on AgentScope

Use `main` for this user's work. Do not create feature branches. Keep the public
landing experience light and amber, and keep `apps/landing` independently buildable.

## Record each development update

Every task that changes the repository must update the public **Phase** timeline
before committing. Summarize the user's requested change and the delivered effect
in plain language; never publish private chat text, credentials, or local data.

- Maintain identical `lib/development-phases.json`, `lib/phase-history.ts`, and
  `components/development-phases.tsx` files in `apps/landing` and `apps/web`.
- Add each new commit to an appropriate phase, with a concise title, concrete
  explanation of what changed, and the UTC commit date. Create a new phase when
  the work starts a distinct milestone.
- For the commit being prepared, use its exact planned commit subject and
  `"sha": null`. The build resolves it to the actual hash and date from Git.
  On the next task, replace that null with the real hash so Git-free and shallow
  builds keep complete commit links. Preserve all existing records.
- Write clear commit subjects. Commits without a curated entry appear automatically
  under **Continued development** when the site builds with Git history available.
- Chat-only discussions do not create commits; record their delivered outcomes
  when implementation occurs. Do not invent dates or completed features.

Check both app typechecks, the standalone landing export verification, and the
landing browser tests after changing the timeline or public navigation.
