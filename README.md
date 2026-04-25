# NB.v1-Chess-Bot
A fully functional chess application featuring a custom Negamax engine and a Pygame GUI. This project implements advanced chess programming techniques, including iterative deepening, transposition tables, and sophisticated move-ordering heuristics.

Estimated ELO (10s move time): ~2000

Note: Changing move time will change strength

# 🚀 Features
The Engine
Search Algorithm: Optimized Negamax with Alpha-Beta pruning.

Iterative Deepening: Searches progressively deeper plies within a time-controlled window.

Aspiration Windows: Speeds up search by narrowing the alpha-beta bounds based on previous iterations.

Transposition Table: Uses Zobrist Hashing to cache and reuse previously evaluated positions, significantly reducing redundant calculations.

Move Ordering: Prioritizes moves using MVV-LVA (Most Valuable Victim - Least Valuable Aggressor), Killer Moves, and History Heuristics to maximize pruning efficiency.

Quiescence Search: Prevents the "horizon effect" by searching through tactical captures and checks until a stable position is reached.

Advanced Pruning: Includes Null-Move Pruning and Check Extensions.

Opening Book: Supports .bin polyglot files (e.g., gm2600.bin) for high-level opening play.

# The Evaluation
The bot uses a "centipawn" scoring system considering:

Material Weights: Weighted values for each piece.

Piece-Square Tables (PST): Position-based bonuses (e.g., knights in the center, pawns advancing).

Tapered Eval: Different evaluation logic for Midgame vs. Endgame (specifically for King safety and positioning).

Pawn Structure: Penalties for doubled or isolated pawns.

King Safety: Shield-based evaluation to protect the king during the midgame.

# The Interface
Real-time Rendering: Built with pygame for a smooth, responsive experience.

Multithreaded: The engine "thinks" on a background thread, so the GUI remains interactive and doesn't freeze during deep searches.

Visual Cues: Highlights legal moves, selected pieces, the last move made, and kings in check.

## Credits
The chess piece images used in this project are sourced from **Green Chess**. 
They are licensed under **Creative Commons Attribution-ShareAlike (CC BY-SA)**.

The opening book file, gm2600.bin, was originally created by Pascal Georges. This specific version was sourced from [DannyStoll1/chess-opening-prep](https://github.com/DannyStoll1/chess-opening-prep).
