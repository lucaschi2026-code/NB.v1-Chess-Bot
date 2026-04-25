import chess
import chess.polyglot
import pygame as pg
import threading
import time

# --- GUI CONSTANTS ---
WIDTH, HEIGHT = 512, 580
SQ_SIZE = WIDTH // 8
LIGHT_COLOUR = (227, 176, 132)
DARK_COLOUR  = (119, 63, 26)
IMAGE = {}

# --- BOT CONFIGURATION ---
OPENING_BOOK_FILE  = "gm2600.bin"
MAX_BOOK_PLY       = 20        # Stop using book after this many half-moves
MAX_DEPTH          = 64        # Effectively unlimited; time control stops the search
BASE_TIME_LIMIT    = 5      
TT_MAX_SIZE        = 2_000_000 # Entries before TT is wiped

# Adaptive time control parameters
TIME_SCALE_OPENING    = 0.7   # Use less time in opening (book is available)
TIME_SCALE_MIDDLEGAME = 1.3   # Use more time in complex middlegame
TIME_SCALE_ENDGAME    = 1.0   # Normal time in endgame
COMPLEXITY_THRESHOLD  = 25    # Number of legal moves to consider position complex

PIECE_VALUES = {
    chess.PAWN:   100,
    chess.KNIGHT: 330,
    chess.BISHOP: 330,
    chess.ROOK:   500,
    chess.QUEEN:  900,
    chess.KING:   20000,
}

# For MVV-LVA the king as an ATTACKER should be treated cheaply.
MVV_LVA_ATTACKER = {
    chess.PAWN:   100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK:   500,
    chess.QUEEN:  900,
    chess.KING:   100,
}

# ---------- Piece-Square Tables (White's perspective, a1=index 0) ----------
PAWN_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]
KNIGHT_TABLE = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]
BISHOP_TABLE = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]
ROOK_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
    20, 20, 20, 20, 20, 20, 20, 20,
     0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  0,  0,
    -10,-10, -5,  0,  0, -5,-10,-10,
]
QUEEN_TABLE = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]
KING_MID_TABLE = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
]
KING_END_TABLE = [
    -50,-40,-30,-20,-20,-30,-40,-50,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -50,-30,-30,-30,-30,-30,-30,-50,
]
PST = {
    chess.PAWN:   PAWN_TABLE,
    chess.KNIGHT: KNIGHT_TABLE,
    chess.BISHOP: BISHOP_TABLE,
    chess.ROOK:   ROOK_TABLE,
    chess.QUEEN:  QUEEN_TABLE,
}

# ---------- Evaluation ----------

def is_endgame(board):
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    if queens == 0:
        return True
    minor_major = sum(
        len(board.pieces(pt, c))
        for pt in (chess.ROOK, chess.BISHOP, chess.KNIGHT)
        for c in (chess.WHITE, chess.BLACK)
    )
    return minor_major <= 2

def get_game_phase(board):
    """Determine game phase for adaptive time management."""
    ply = board.ply()
    if ply < MAX_BOOK_PLY:
        return "opening"
    elif is_endgame(board):
        return "endgame"
    else:
        return "middlegame"

def material_score(board):
    score = 0
    for pt, val in PIECE_VALUES.items():
        score += val * (len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK)))
    return score

def piece_square_score(board, endgame):
    score = 0
    king_table = KING_END_TABLE if endgame else KING_MID_TABLE
    for pt, table in PST.items():
        for sq in board.pieces(pt, chess.WHITE):
            score += table[sq ^ 56]
        for sq in board.pieces(pt, chess.BLACK):
            score -= table[sq]
    for sq in board.pieces(chess.KING, chess.WHITE):
        score += king_table[sq ^ 56]
    for sq in board.pieces(chess.KING, chess.BLACK):
        score -= king_table[sq]
    return score

def pawn_structure_score(board):
    """Enhanced pawn structure scoring."""
    score = 0
    wp_set = board.pieces(chess.PAWN, chess.WHITE)
    bp_set = board.pieces(chess.PAWN, chess.BLACK)
    
    wp = list(wp_set)
    bp = list(bp_set)
    
    for f in range(8):
        wp_f = [s for s in wp if chess.square_file(s) == f]
        bp_f = [s for s in bp if chess.square_file(s) == f]
        
        adj_files = set()
        if f > 0: adj_files.add(f - 1)
        if f < 7: adj_files.add(f + 1)
        
        wp_adjacent = [s for s in wp if chess.square_file(s) in adj_files]
        bp_adjacent = [s for s in bp if chess.square_file(s) in adj_files]
        
        if len(wp_f) > 1: score -= 20
        if len(bp_f) > 1: score += 20
        
        if wp_f and not wp_adjacent: score -= 25
        if bp_f and not bp_adjacent: score += 25
    
    for sq in wp:
        sq_file = chess.square_file(sq)
        sq_rank = chess.square_rank(sq)
        passed = True
        for bp_sq in bp:
            bp_file = chess.square_file(bp_sq)
            bp_rank = chess.square_rank(bp_sq)
            if bp_rank > sq_rank and abs(bp_file - sq_file) <= 1:
                passed = False
                break
        if passed:
            score += 40
    
    for sq in bp:
        sq_file = chess.square_file(sq)
        sq_rank = chess.square_rank(sq)
        passed = True
        for wp_sq in wp:
            wp_file = chess.square_file(wp_sq)
            wp_rank = chess.square_rank(wp_sq)
            if wp_rank > sq_rank and abs(wp_file - sq_file) <= 1:
                passed = False
                break
        if passed:
            score -= 40
    
    center_pawns_white = [s for s in wp if chess.square_file(s) in (3, 4)]
    center_pawns_black = [s for s in bp if chess.square_file(s) in (3, 4)]
    score += 5 * len(center_pawns_white)
    score -= 5 * len(center_pawns_black)
    
    return score

def king_safety_score(board, endgame):
    """Enhanced king safety with castling evaluation and attack patterns."""
    if endgame:
        return 0
    score = 0
    for color in (chess.WHITE, chess.BLACK):
        ks = board.king(color)
        if ks is None:
            continue
        
        kf = chess.square_file(ks)
        kr = chess.square_rank(ks)
        sign = -1 if color == chess.WHITE else 1
        
        # Strongly prefer castled kings
        if ks in (chess.G1, chess.C1, chess.G8, chess.C8):
            score += sign * 60  # Castled
        elif ks in (chess.E1, chess.E8):
            score -= sign * 25  # Still in center - penalty
        elif kr == 0 or kr == 7:
            score -= sign * 15  # Back rank but not castled
        
        # Pawn shield
        shield_squares = []
        if color == chess.WHITE:
            for dr in [-1, 0]:
                sq = ks - 8 + dr
                if 0 <= sq < 64:
                    shield_squares.append(sq)
                sq = ks - 16 + dr
                if 0 <= sq < 64:
                    shield_squares.append(sq)
        else:
            for dr in [-1, 0]:
                sq = ks + 8 + dr
                if 0 <= sq < 64:
                    shield_squares.append(sq)
                sq = ks + 16 + dr
                if 0 <= sq < 64:
                    shield_squares.append(sq)
        
        pawns_on_shield = 0
        for sq in shield_squares:
            p = board.piece_at(sq)
            if p and p.piece_type == chess.PAWN and p.color == color:
                pawns_on_shield += 1
        
        if pawns_on_shield == 0:
            score += sign * 60
        elif pawns_on_shield == 1:
            score += sign * 25
        elif pawns_on_shield == 2:
            score += sign * 10
        
        # Penalty for moved king
        if (color == chess.WHITE and ks not in (chess.E1, chess.G1, chess.C1)) or \
           (color == chess.BLACK and ks not in (chess.E8, chess.G8, chess.C8)):
            rooks = board.pieces(chess.ROOK, color)
            if color == chess.WHITE:
                if not (chess.A1 in rooks or chess.H1 in rooks):
                    score -= sign * 30
            else:
                if not (chess.A8 in rooks or chess.H8 in rooks):
                    score -= sign * 30
        
        # Open file toward king
        king_file_squares = []
        for r in range(8):
            king_file_squares.append(chess.square(kf, r))
        
        has_enemy_pawn_on_file = False
        for sq in king_file_squares:
            p = board.piece_at(sq)
            if p and p.piece_type == chess.PAWN and p.color != color:
                has_enemy_pawn_on_file = True
                break
        
        if not has_enemy_pawn_on_file:
            score -= sign * 15
        
        # Attackers near king
        enemy = chess.BLACK if color == chess.WHITE else chess.WHITE
        for df in [-1, 0, 1]:
            for dr in [-1, 0, 1]:
                if df == 0 and dr == 0:
                    continue
                af = kf + df
                ar = kr + dr
                if 0 <= af < 8 and 0 <= ar < 8:
                    attack_sq = chess.square(af, ar)
                    attacker = board.piece_at(attack_sq)
                    if attacker and attacker.color == enemy:
                        piece_val = PIECE_VALUES.get(attacker.piece_type, 0)
                        if piece_val >= 330:
                            score -= sign * 20
    
    # Penalty for rooks stuck in corners (h8/g8 oscillation for black)
    # Encourage rooks to leave corner squares and active play
    # Black rooks: avoid a8, b8, g8, h8 (starting squares and adjacent)
    # White rooks: avoid a1, b1, g1, h1
    corner_squares_white = (chess.A1, chess.H1)
    corner_squares_black = (chess.A8, chess.H8)
    adjacent_to_corner_white = (chess.B1, chess.G1)
    adjacent_to_corner_black = (chess.B8, chess.G8)
    
    for rook_sq in board.pieces(chess.ROOK, chess.WHITE):
        if rook_sq in corner_squares_white:
            score -= 30  # Penalty for corner rook
        elif rook_sq in adjacent_to_corner_white:
            score -= 15  # Penalty for rook on square adjacent to corner
    for rook_sq in board.pieces(chess.ROOK, chess.BLACK):
        if rook_sq in corner_squares_black:
            score += 30  # Penalty for black rook in corner
        elif rook_sq in adjacent_to_corner_black:
            score += 15  # Penalty for black rook adjacent to corner
    
    # Bonus for castling - encourage keeping king safe
    for color in (chess.WHITE, chess.BLACK):
        ks = board.king(color)
        if ks is not None:
            sign = -1 if color == chess.WHITE else 1
            # King castled = good for that side
            if ks in (chess.G1, chess.C1, chess.G8, chess.C8):
                score += sign * 20
    
    return score

def evaluate_board(board):
    """Static evaluation in centipawns, from the side-to-move's perspective."""
    eg  = is_endgame(board)
    raw = (material_score(board)
           + piece_square_score(board, eg)
           + pawn_structure_score(board)
           + king_safety_score(board, eg))
    return raw if board.turn == chess.WHITE else -raw

# ---------- Search state ----------

TT_EXACT = 0
TT_LOWER = 1
TT_UPPER = 2

MAX_KILLERS_DEPTH = 64
transposition_table = {}
killer_moves        = [[None, None] for _ in range(MAX_KILLERS_DEPTH)]
history_table       = {}   # persists across moves for better ordering
search_stopped      = False
search_start        = 0.0
time_limit          = BASE_TIME_LIMIT  # Will be set adaptively per move

def _time_up():
    return time.time() - search_start >= time_limit

# ---------- Move ordering ----------

def order_moves(board, depth, tt_move=None):
    def _score(move):
        if move == tt_move:
            return 30_000
        if board.is_capture(move):
            victim    = board.piece_at(move.to_square)
            aggressor = board.piece_at(move.from_square)
            if victim and aggressor:
                return (10_000
                        + 10 * PIECE_VALUES[victim.piece_type]
                        - MVV_LVA_ATTACKER[aggressor.piece_type])
            return 10_000
        d = min(depth, MAX_KILLERS_DEPTH - 1)
        if move == killer_moves[d][0]: return 9_000
        if move == killer_moves[d][1]: return 8_000
        if move.promotion == chess.QUEEN: return 7_000
        return history_table.get((move.from_square, move.to_square), 0)
    return sorted(board.legal_moves, key=_score, reverse=True)

def _update_killers(move, depth):
    d = min(depth, MAX_KILLERS_DEPTH - 1)
    if killer_moves[d][0] != move:
        killer_moves[d][1] = killer_moves[d][0]
        killer_moves[d][0] = move

def _update_history(move, depth):
    key = (move.from_square, move.to_square)
    history_table[key] = history_table.get(key, 0) + depth * depth

# ---------- Quiescence search ----------

def quiescence(board, alpha, beta, qdepth=0):
    """Enhanced quiescence search with proper terminal detection."""
    # Detect checkmate / stalemate inside quiescence
    if board.is_game_over():
        if board.is_checkmate():
            return -99_000 + board.ply()
        return 0

    in_check  = board.is_check()
    stand_pat = evaluate_board(board)

    if not in_check:
        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

    # Adaptive quiescence depth based on position complexity
    max_qdepth = 15 if in_check else 12
    if qdepth > max_qdepth:
        return stand_pat

    for move in board.legal_moves:
        is_cap   = board.is_capture(move)
        is_promo = bool(move.promotion)

        # When in check, search ALL legal moves (evasions)
        if not in_check and not is_cap and not is_promo:
            continue

        # Delta pruning: skip hopeless quiet captures
        if not in_check and is_cap and not is_promo:
            victim = board.piece_at(move.to_square)
            if victim and stand_pat + PIECE_VALUES[victim.piece_type] + 200 < alpha:
                continue

        board.push(move)
        score = -quiescence(board, -beta, -alpha, qdepth + 1)
        board.pop()

        if score >= beta:
            return beta
        if score > alpha:
            alpha = score

    return alpha

# ---------- Negamax with advanced pruning ----------

def negamax(board, depth, alpha, beta, do_null=True):
    """Enhanced negamax with multiple pruning techniques."""
    global search_stopped

    if search_stopped or _time_up():
        search_stopped = True
        return 0

    hash_key   = chess.polyglot.zobrist_hash(board)
    tt_move    = None
    orig_alpha = alpha

    # Transposition table lookup
    if hash_key in transposition_table:
        tt_depth, tt_score, tt_flag, tt_mv = transposition_table[hash_key]
        if tt_depth >= depth:
            if tt_flag == TT_EXACT:
                return tt_score
            elif tt_flag == TT_LOWER:
                alpha = max(alpha, tt_score)
            elif tt_flag == TT_UPPER:
                beta  = min(beta,  tt_score)
            if alpha >= beta:
                return tt_score
        tt_move = tt_mv

    # Terminal position detection
    if board.is_game_over():
        if board.is_checkmate():
            return -99_000 + board.ply()
        return 0

    # Quiescence search at horizon
    if depth == 0:
        return quiescence(board, alpha, beta)

    in_check = board.is_check()
    
    # Razoring - CONSERVATIVE to prevent blunders
    if depth == 1 and not in_check and not board.is_checkmate():
        eval_score = evaluate_board(board)
        if eval_score + 400 < alpha:
            qscore = quiescence(board, alpha, beta)
            if qscore < alpha:
                return qscore

    # Futility pruning - CONSERVATIVE: only skip very hopeless quiet moves
    futility_prune = False
    if depth == 1 and not in_check:
        eval_score = evaluate_board(board)
        futility_margin = 300  # Safe margin
        if eval_score + futility_margin < alpha:
            futility_prune = True

    # Null-move pruning (skip when in check or near endgame)
    non_pawn = sum(
        len(board.pieces(pt, board.turn))
        for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
    )
    if do_null and depth >= 3 and not in_check and non_pawn >= 1:
        R = 2
        board.push(chess.Move.null())
        null_score = -negamax(board, depth - 1 - R, -beta, -beta + 1, do_null=False)
        board.pop()
        if not search_stopped and null_score >= beta:
            return beta

    moves      = order_moves(board, depth, tt_move)
    best_score = -float('inf')
    best_move  = None
    moves_done = 0

    for move in moves:
        # Futility pruning: skip quiet moves that can't help
        if (futility_prune 
                and moves_done > 0
                and not board.is_capture(move)
                and not move.promotion
                and not board.gives_check(move)):
            continue

        board.push(move)
        gives_check = board.is_check()
        
        # --- SELECTIVE EXTENSIONS ---
        extension = 0
        
        # Check extension
        if gives_check:
            extension = 1
        # Pawn to 7th rank (near promotion)
        if move.from_square is not None:
            piece = board.piece_at(move.to_square)
            if piece and piece.piece_type == chess.PAWN:
                to_rank = chess.square_rank(move.to_square)
                if (piece.color == chess.WHITE and to_rank == 6) or \
                   (piece.color == chess.BLACK and to_rank == 1):
                    extension = 1
        # Recapture extension (capture on same square as last move)
        if board.move_stack and len(board.move_stack) >= 2:
            if board.is_capture(move):
                last_move = board.move_stack[-2]
                if move.to_square == last_move.to_square:
                    extension = 1

        # First move gets full search
        if moves_done == 0:
            score = -negamax(board, depth - 1 + extension, -beta, -alpha)
        else:
            # --- LATE MOVE REDUCTION (LMR) ---
            reduction = 0
            if (depth >= 3
                    and moves_done >= 4
                    and not gives_check
                    and not in_check
                    and not board.is_capture(move)
                    and not move.promotion):
                # More conservative LMR for better move stability
                reduction = 1
                if moves_done >= 8:
                    reduction = 2
                # Don't reduce killer moves as much
                d = min(depth, MAX_KILLERS_DEPTH - 1)
                if move in killer_moves[d]:
                    reduction = max(0, reduction - 1)

            # PVS: null window search
            score = -negamax(board, depth - 1 + extension - reduction, -alpha - 1, -alpha)

            # Re-search if it beat alpha or was reduced
            if not search_stopped and (score > alpha or reduction > 0):
                score = -negamax(board, depth - 1 + extension, -beta, -alpha)

        board.pop()

        if search_stopped:
            break

        moves_done += 1

        if score > best_score:
            best_score = score
            best_move  = move

        if score > alpha:
            alpha = score

        if alpha >= beta:
            if not board.is_capture(move):
                _update_killers(move, depth)
                _update_history(move, depth)
            break

    # Store in transposition table
    if not search_stopped and best_move is not None:
        flag = (TT_UPPER if best_score <= orig_alpha else
                TT_LOWER if best_score >= beta       else
                TT_EXACT)
        transposition_table[hash_key] = (depth, best_score, flag, best_move)

    return best_score

# ---------- Iterative Deepening root ----------

def calculate_time_for_move(board):
    """Adaptive time allocation based on game phase and position complexity."""
    phase = get_game_phase(board)
    
    # Increase base time to ensure deeper searches
    base_multiplier = 1.0  # Increased from 0.6 to ensure minimum depth
    
    if phase == "opening":
        multiplier = base_multiplier * TIME_SCALE_OPENING
    elif phase == "middlegame":
        multiplier = base_multiplier * TIME_SCALE_MIDDLEGAME
    else:  # endgame
        multiplier = base_multiplier * TIME_SCALE_ENDGAME
    
    # Adjust based on position complexity (number of legal moves)
    num_legal_moves = board.legal_moves.count()
    if num_legal_moves > COMPLEXITY_THRESHOLD:
        multiplier *= 1.3  # Complex position: think longer
    elif num_legal_moves < 10:
        multiplier *= 0.7  # Simple position: think less
    
    return BASE_TIME_LIMIT * multiplier

def get_best_move(board):
    global transposition_table, killer_moves, search_stopped, search_start, time_limit

    # Opening book — only for the first MAX_BOOK_PLY half-moves
    if board.ply() < MAX_BOOK_PLY:
        try:
            with chess.polyglot.open_reader(OPENING_BOOK_FILE) as reader:
                entry = reader.weighted_choice(board)
                print(f"Book move: {entry.move}")
                return entry.move
        except Exception:
            pass

    # Wipe TT when it gets too large (avoid memory bloat); keep history_table
    if len(transposition_table) > TT_MAX_SIZE:
        transposition_table = {}
    killer_moves   = [[None, None] for _ in range(MAX_KILLERS_DEPTH)]
    search_stopped = False
    search_start   = time.time()
    
    # Adaptive time allocation
    time_limit = calculate_time_for_move(board)
    phase = get_game_phase(board)
    print(f"Phase: {phase}, Time allocated: {time_limit:.2f}s")

    best_move  = list(board.legal_moves)[0]
    prev_score = 0

    # Start search at depth 3 minimum - never search at depth 1 or 2
    for depth in range(3, MAX_DEPTH + 1):
        if search_stopped or _time_up():
            break

        # Aspiration windows - wider for stability
        if depth == 3:
            delta = 100  # Wider for low depths
            asp_alpha = prev_score - delta
            asp_beta  = prev_score + delta
        else:
            delta = 50  # Normal for deeper
            asp_alpha = prev_score - delta
            asp_beta  = prev_score + delta

        while True:
            depth_best  = None
            depth_score = -float('inf')

            root_moves = order_moves(board, depth)

            for i, move in enumerate(root_moves):
                board.push(move)

                if i == 0:
                    score = -negamax(board, depth - 1, -asp_beta, -asp_alpha)
                else:
                    # PVS at root
                    score = -negamax(board, depth - 1, -depth_score - 1, -depth_score)
                    if not search_stopped and score > depth_score:
                        score = -negamax(board, depth - 1, -asp_beta, -depth_score)

                board.pop()

                if search_stopped:
                    break

                if score > depth_score:
                    depth_score = score
                    depth_best  = move

            if search_stopped:
                break

            # Widen aspiration window if needed
            if depth >= 4:
                if depth_score <= asp_alpha:
                    asp_alpha = max(-float('inf'), asp_alpha - delta * 2)
                    delta *= 3
                elif depth_score >= asp_beta:
                    asp_beta = min(float('inf'), asp_beta + delta * 2)
                    delta *= 3
                else:
                    break
            else:
                break

            if _time_up():
                search_stopped = True
                break

        if not search_stopped and depth_best is not None:
            best_move  = depth_best
            prev_score = depth_score
            elapsed    = time.time() - search_start
            print(f"  depth {depth:2d} | {best_move} | score {depth_score:+6.0f} | {elapsed:.2f}s")

        # Early stopping after minimum depth of 3 is always completed
        elapsed = time.time() - search_start
        if depth >= 3 and elapsed >= time_limit * 0.5:
            break
        if depth >= 6 and elapsed >= time_limit * 0.7:
            break

    elapsed_total = time.time() - search_start
    print(f"Total time: {elapsed_total:.2f}s, Final move: {best_move}")
    return best_move

# ---------- GUI ----------

def load_images():
    pieces = ["wP","wN","wB","wR","wQ","wK","bP","bN","bB","bR","bQ","bK"]
    for p in pieces:
        img = pg.image.load("images/" + p + ".png")
        IMAGE[p] = pg.transform.smoothscale(img, (int(SQ_SIZE), int(SQ_SIZE)))

def draw_status(screen, board, font):
    pg.draw.rect(screen, (50, 50, 50), (0, 0, WIDTH, 68))
    if board.is_checkmate():
        winner = "Black Wins!" if board.turn == chess.WHITE else "White Wins!"
        screen.blit(font.render(winner, True, (255, 0, 0)), (10, 10))
    elif board.is_game_over():
        screen.blit(font.render("Draw!", True, (255, 255, 0)), (10, 10))
    else:
        txt = "White's Turn" if board.turn == chess.WHITE else "Bot is thinking..."
        screen.blit(font.render(txt, True, (255, 255, 255)), (10, 10))

def draw_board(screen):
    for r in range(8):
        for c in range(8):
            colour = LIGHT_COLOUR if (r + c) % 2 == 0 else DARK_COLOUR
            pg.draw.rect(screen, colour,
                         pg.Rect(c * SQ_SIZE, r * SQ_SIZE + 68, SQ_SIZE, SQ_SIZE))

def draw_pieces(screen, board):
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            key = ('w' if piece.color == chess.WHITE else 'b') + piece.symbol().upper()
            col = chess.square_file(square)
            row = 7 - chess.square_rank(square)
            screen.blit(IMAGE[key], (col * SQ_SIZE, row * SQ_SIZE + 68))
    if board.is_check() or board.is_checkmate():
        ks = board.king(board.turn)
        if ks:
            pg.draw.rect(screen, (255, 0, 0),
                (chess.square_file(ks) * SQ_SIZE,
                 (7 - chess.square_rank(ks)) * SQ_SIZE + 68,
                 SQ_SIZE, SQ_SIZE), 6)

def main():
    pg.init()
    load_images()
    screen = pg.display.set_mode((WIDTH, HEIGHT))
    pg.display.set_caption("Chess Bot - Enhanced")
    font  = pg.font.SysFont("Arial", 32, bold=True)
    clock = pg.time.Clock()

    board           = chess.Board()
    selected_square = None
    last_move       = None
    running         = True
    bot_move        = None
    bot_thinking    = False

    def calculate_bot_move(position):
        nonlocal bot_move, bot_thinking
        bot_move     = get_best_move(position)
        bot_thinking = False

    while running:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False
            if (event.type == pg.MOUSEBUTTONDOWN
                    and board.turn == chess.WHITE
                    and not board.is_game_over()):
                pos = pg.mouse.get_pos()
                if pos[1] > 68:
                    col = pos[0] // SQ_SIZE
                    row = 7 - ((pos[1] - 68) // SQ_SIZE)
                    if 0 <= col < 8 and 0 <= row < 8:
                        clicked = chess.square(col, row)
                        if selected_square is None:
                            if (board.piece_at(clicked)
                                    and board.piece_at(clicked).color == chess.WHITE):
                                selected_square = clicked
                        else:
                            move  = chess.Move(selected_square, clicked)
                            promo = chess.Move(selected_square, clicked, promotion=chess.QUEEN)
                            if move in board.legal_moves or promo in board.legal_moves:
                                if move not in board.legal_moves:
                                    move.promotion = chess.QUEEN
                                board.push(move)
                                last_move, selected_square = move, None
                            elif (board.piece_at(clicked)
                                  and board.piece_at(clicked).color == chess.WHITE):
                                selected_square = clicked
                            else:
                                selected_square = None

        draw_status(screen, board, font)
        draw_board(screen)
        if last_move:
            for s in (last_move.from_square, last_move.to_square):
                pg.draw.rect(screen, (0, 100, 255),
                    (chess.square_file(s) * SQ_SIZE,
                     (7 - chess.square_rank(s)) * SQ_SIZE + 68,
                     SQ_SIZE, SQ_SIZE), 4)
        draw_pieces(screen, board)
        if selected_square is not None:
            pg.draw.rect(screen, (255, 255, 0),
                (chess.square_file(selected_square) * SQ_SIZE,
                 (7 - chess.square_rank(selected_square)) * SQ_SIZE + 68,
                 SQ_SIZE, SQ_SIZE), 4)
        pg.display.flip()

        if bot_move is not None and board.turn == chess.BLACK:
            board.push(bot_move)
            last_move = bot_move
            bot_move  = None

        if (not board.is_game_over()
                and board.turn == chess.BLACK
                and not bot_thinking
                and bot_move is None):
            bot_thinking = True
            threading.Thread(
                target=calculate_bot_move,
                args=(board.copy(),),
                daemon=True
            ).start()

        clock.tick(60)

    pg.quit()

if __name__ == "__main__":
    main()
