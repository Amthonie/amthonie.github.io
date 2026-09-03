---
id: 19
date: 2026-09-03
slug: sight-reading-the-system
tags: [coding, music, reflection]
title: Sight-Reading the System
summary: Why I treat code as a music score, and what follows from it.
image: 19-sight-reading-the-system.webp
image_alt: Retro magazine style illustration of a 1950s computer room where a conductor stands on a podium, baton raised, directing programmers at their terminals instead of musicians. Behind him a whiteboard shows a flowchart on the left turning into four staves of music on the right. Open binders on stands in the foreground are labelled VOICE 1, VOICE 2, THEME A and BAR 94. Everyone is working cheerfully and in step.
image_caption: A fugue for terminals.
---

Nobody ever taught me to write software. I read musicology, not computer science, and my first serious programming was spent coaxing three voices of Bach out of a Commodore 64 — three being what the sound chip allowed and, conveniently, what a fugue requires. Fifteen years of writing and debugging code for a living have not dislodged that training. It still does most of the structural work.

So that is where I begin. The rule I keep returning to is that every class or function should do one thing, and do it as brilliantly and independently as possible.

There is a well-worn line that good code reads like a book. It doesn't, and it shouldn't. A book is read once, at leisure, for its content. A score is read while being performed — by someone who was not in the room when it was written, usually at the least convenient moment available. Everything on the page is therefore functional rather than decorative. Rehearsal marks exist so that a player can restart at bar 94 without a search party.

A class, in that reading, is a theme. Like a fugue subject it turns up in several places and in different shapes and remains recognisably the same thing, which is why a subject that only works where it was first stated is a poor subject. The writing of it already anticipates being developed. That is not the same as bolting on machinery for a caller who does not yet exist; one keeps a theme portable by writing it cleanly, not by adding to it.

The rest follows from how a score is laid out. A full score shows every voice at once, so the shape is legible at a glance, while the parts carry the detail — which is exactly how a main method ought to read, with the steps visible at the top and the particulars further down. And debugging is simply the conductor stopping the orchestra at bar 94 to see what each line is playing at that moment, which is an argument for state you can take in whole rather than assemble from a dozen scattered variables.

None of which is really about elegance. My actual reason is less refined: when I no longer understand a piece of code, that is a red flag rather than an inconvenience. If the reader has lost the thread, the author has very probably lost it too, and there is no more comfortable place for a bug to sit unnoticed. Nobody scrutinises the passage they have quietly given up reading.

There is a decent argument against all this: hunting through eight tidily named methods can cost more than reading one long one. My answer is that a score manages both: the parts separate the voices, and the full score puts every voice for a single moment on one page.

Having finally written this down, I discovered most of it already has names — Parnas in 1972, Kent Beck's composed method, a good half of Code Complete. Reassuring, and mildly deflating, depending on the hour. One can apparently arrive at software engineering orthodoxy by way of the well-tempered clavier. It simply takes longer, and has better tunes.
