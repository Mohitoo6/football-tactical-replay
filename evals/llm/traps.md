# Coach explanations: trap tests

Each trap takes the facts of Musiala's winner, changes one thing, and asks the coach again. A faithful coach must follow the changed facts. Made by `scripts/evaluate_explanations.py --traps`.

| Trap | What the coach must do | Result | Grounded | Model |
|---|---|---|---|---|
| no-goal | The goal is removed: the coach must not mention a goal or a scorer. | PASS | yes | gemini-3.8-flash |
| too-little-play | Only 3 s of open play and no timeline: the coach must say there is too little play to analyse. | PASS | yes | gemini-3.8-flash |
| unknown-shape | The focus team's shape is unknown: the coach must not name 4-1-4-1 for it. | PASS | yes | gemini-3.8-flash |
| partial-camera | The camera shows only part of the pitch: the coach must say so. | PASS | yes | gemini-3.8-flash |
| mirror-numbers | Both teams' width moves between 35 and 44 m, in opposite directions: each number must stay with its team. | PASS | yes | gemini-3.8-flash |

**5/5 traps passed.** The answers are in `evals/llm/traps/`.

## no-goal (PASS)

**What happened**  
In this clip, FC Bayern München showed a 4-1-4-1 shape and 1. FC Köln showed a 3-5-2 shape. The ball moved from Leroy Sané at 87:57 to M. Schwäbe at 88:00, Jeff Chabot at 88:03, Joshua Kimmich at 88:03, Joao Cancelo at 88:07, Serge Gnabry at 88:09, and J. Musiala at 88:12. Bayern pushed their back line (the average distance of the four deepest outfield defenders from their goal line) from 42 metres at 87:57 up to 72 metres at 88:13, while Köln’s back line retreated from 25 metres to 10 metres.

**Coach's view**  
* Bayern pushing their back line up to 72 metres while reducing team depth from 49 to 32 metres suggests high pressure that helped regain possession in midfield through Joshua Kimmich.  
* Köln’s shape compressed to 388 m² and 26 metres depth at 88:13; typically, this deep block protects the central box but gives away space on the flanks, allowing Bayern to reach 51 metres width at 88:09.

**Key numbers**  
* Bayern's back line advanced from 42 m to 72 m.  
* Köln's area decreased from 757 m² to 388 m².  
* Bayern expanded their width from 35 m to 51 m.

## too-little-play (PASS)

**What happened**  
The clip runs from 87:57 to 88:20, with FC Bayern München showing a 4-1-4-1 shape and 1. FC Köln showing a 3-5-2 shape. The ball moved from Leroy Sané to M. Schwäbe at 88:00, then to Jeff Chabot and Joshua Kimmich at 88:03, followed by Joao Cancelo at 88:07, Serge Gnabry at 88:09, and J. Musiala at 88:12. J. Musiala scored a goal for FC Bayern München at 88:15.

**Coach's view**  
- There was too little open play to analyse tactical patterns in detail, as the ball was in play for only 3 seconds and the timeline is empty.  
- Bayern München rapidly moved the ball through several players—Kimmich, Cancelo, Gnabry, and Musiala—which typically disrupts an opponent before they can organise defensively.  
- Köln’s shape in the clip was a 3-5-2, and a coach would ask how the defending team allowed the ball to progress quickly into the path of Musiala inside the final third.

**Key numbers**  
- Seconds ball in play: 3 (out of 23 clip seconds).  
- Goal scored: J. Musiala at 88:15.  
- Players on the pitch: 11 for FC Bayern München, 11 for 1. FC Köln.

## unknown-shape (PASS)

**What happened**  
Across 17 seconds of open play, the ball travelled from Leroy Sané to M. Schwäbe, Jeff Chabot, Joshua Kimmich, Joao Cancelo, Serge Gnabry, and finally J. Musiala, who scored for FC Bayern München at 88:15. During this attack, Bayern pushed their back line—the average distance of their four deepest outfield players from their own goal line—from 42 metres at 87:57 up to 72 metres at 88:13. Meanwhile, 1. FC Köln defended in a 3-5-2 shape in this clip, retreating their back line from 25 metres to 10 metres and compressing their team area from 757 m² to 388 m².

**Coach's view**  
• FC Bayern München squeezed the pitch by advancing their back line to 72 metres, which typically keeps pressure high and pins an opponent inside their own half.  
• 1. FC Köln dropped into a very deep, compact block with their back line at 10 metres; while this protects the space right in front of goal, it often surrenders room outside the penalty area for attacking players to operate.

**Key numbers**  
• FC Bayern München back line height: moved from 42 m up to 72 m.  
• 1. FC Köln team area: contracted from 757 m² down to 388 m².  
• Goal scored: J. Musiala at 88:15.

## partial-camera (PASS)

**What happened**  
Note that the broadcast camera showed only part of the pitch, so shape measurements describe visible players. FC Bayern München set up in a 4-1-4-1 shape in this clip, while 1. FC Köln showed a 3-5-2. The ball moved across several players: Leroy Sané at 87:57, M. Schwäbe at 88:00, Jeff Chabot and Joshua Kimmich at 88:03, Joao Cancelo at 88:07, Serge Gnabry at 88:09, and finally J. Musiala at 88:12, who scored a goal at 88:15. During this sequence, Bayern pushed their back line (the average distance of the four deepest outfield players from their own goal line) forward from 42 m at 87:57 to 72 m at 88:13, while Köln’s back line retreated from 25 m to 10 m.

**Coach's view**  
* Bayern’s aggressive positioning—advancing their back line to 72 m and compressing their depth from 49 m to 32 m—suggests they successfully pinned Köln into their defensive third to sustain the attack.  
* Köln’s retreat to a deep 10 m back line and an area of 388 m² indicates a compact low block, but retreating so deep typically concedes control of the edge of the penalty box.

**Key numbers**  
* Bayern back-line height: pushed up from 42 m to 72 m.  
* Köln team area: shrank from 757 m² to 388 m².  
* Goal scored: J. Musiala at 88:15.

## mirror-numbers (PASS)

**What happened**  
From 87:57 to 88:20, FC Bayern München showed a 4-1-4-1 shape, and 1. FC Köln showed a 3-5-2 shape. The ball moved through Leroy Sané, M. Schwäbe, Jeff Chabot, Joshua Kimmich, Joao Cancelo, Serge Gnabry, and J. Musiala, who scored a goal at 88:15. FC Bayern München moved their back line—the average distance of the four deepest outfield players from their own goal line—from 42 m at 87:57 up to 72 m at 88:13, while 1. FC Köln's back line dropped from 25 m to 10 m.

**Coach's view**  
* FC Bayern München expanding their width from 35 m to 44 m typically stretches defensive coverage across the pitch, creating room to attack.  
* Pushing the back line up to 72 m suggests FC Bayern München committed players forward to keep 1. FC Köln pinned deep.  
* 1. FC Köln retreated into a compact 388 m² area with a back line at 10 m by 88:13; defending so deep typically surrenders central control and leaves little margin for error around the box.

**Key numbers**  
* Goal: J. Musiala at 88:15.  
* FC Bayern München width: 35 m to 44 m.  
* Back line distance at 88:13: FC Bayern München 72 m, 1. FC Köln 10 m.

