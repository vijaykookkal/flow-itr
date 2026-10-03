# Document skills

A skill is what an experienced reader knows about one kind of document: how to
recognise it, where its transactions sit, and the traps in its layout. It is
not a parser. The engine still reads every document with the same generic
skill; a skill file only saves it from rediscovering, every year, that a
particular statement repeats its year-to-date figures or stacks nine tables in
one sheet.

## How the engine uses them

Every extraction prompt lists the skills below by `name` and `use_when`. When
the engine meets a document that fits one, it reads that skill's file before
reading the document. Nothing in code matches file names to skills: a broker
renames its export, or a bank statement arrives called "dividend_statement",
and recognising it from its contents is the engine's job.

## Adding one

Copy an existing file, keep the front matter, and write down only what you
have seen in a real document. Mark anything you have not verified as such.
A skill that is confidently wrong is worse than no skill, because it overrides
what the engine would otherwise have read correctly.

Front matter:

    ---
    name: short-kebab-name
    use_when: One sentence a reader can check against a document's first page.
    schedules: [capital_gains, other_sources, ...]
    verified_from: what real document this was written from
    ---
