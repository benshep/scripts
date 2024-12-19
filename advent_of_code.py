import os
import numpy as np
import re
from functools import cmp_to_key
from operator import mul, add
from collections import Counter, defaultdict
from time import sleep
from folders import downloads_folder


go_up = "\033[F"

def puzzle_2023(day, part):
    puzzle_input = open(os.path.join(downloads_folder, f'{day=}.txt')).read().splitlines()
    puzzle_input = '''two1nine
eightwothree
abcone2threexyz
xtwone3four
4nineeightseven2
zoneight234
7pqrstsixteen
'''.splitlines()
    if day == 1:  # Trebuchet?!
        total = 0
        all_digits = 'zero|one|two|three|four|five|six|seven|eight|nine'
        for line in puzzle_input:

            if part != 1:
                re.match(all_digits, line)
            digits = [char for char in line if char in '0123456789']

            calibration_value = int(digits[0] + digits[-1])
            print(line, calibration_value)
            total += calibration_value
        print(total)


def puzzle_2024(day, part, test_input='', split=True):
    puzzle_input = test_input or open(os.path.join(downloads_folder, f'{day=}.txt')).read()
    if split:
        puzzle_input = puzzle_input.splitlines()
    else:
        puzzle_input = puzzle_input.strip('\n')
    rows = len(puzzle_input)
    cols = {len(line) for line in puzzle_input}
    if len(cols) == 1:
        cols = cols.pop()
        print(f'{rows=} {cols=}')
        original_layout = np.array([list(line) for line in puzzle_input], dtype='S1')
    if day == 1:  # Historian Hysteria
        left, right = zip(*[line.split('   ') for line in puzzle_input])
        left = sorted(int(i) for i in left)
        right = sorted(int(i) for i in right)
        if part == 1:
            return sum(abs(r - l) for l, r in zip(left, right))
        else:
            return sum(l * right.count(l) for l in left)
    elif day == 2:  # Red-Nosed Reports
        safe_reports = 0
        for line in puzzle_input:
            split = line.split(' ')
            for i in range(-1, len(split)):
                levels = [int(l) for l in split]
                if i >= 0 and part == 2:
                    levels.pop(i)
                diffs = np.diff(levels)
                if (all(diffs > 0) or all(diffs < 0)) and min(abs(diffs)) >= 1 and max(abs(diffs)) <= 3:
                    safe_reports += 1
                    break
                if part == 1: break
        return safe_reports
    elif day == 3:  # Mull It Over
        matches = re.findall(r"(mul|do|don't)\((?:(\d+),(\d+))?\)", puzzle_input)
        total = 0
        enabled = True
        for instruction, a, b in matches:
            print(instruction, a, b)
            if instruction == "don't":
                enabled = False
            elif instruction == 'do':
                enabled = True
            elif instruction == 'mul' and (enabled or part == 1):
                total += int(a) * int(b)
        return total
    elif day == 4:  # Ceres Search
        word = b'XMAS'
        grid = np.array(puzzle_input, dtype=bytes)
        grid = grid.view('S1').reshape((grid.size, -1))
        rows, cols = grid.shape
        count = 0
        if part == 1:
            for r in range(rows):
                for c in range(cols):
                    for dr, dc in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
                        for i in range(len(word)):
                            rr = r + dr * i
                            cc = c + dc * i
                            if rr < 0 or cc < 0 or rr >= rows or cc >= cols or grid[rr, cc] != word[i].to_bytes():
                                break
                        else:
                            print(r, c, dr, dc)
                            count += 1
        else:
            patterns = (b'M.S.A.M.S', b'S.S.A.M.M', b'M.M.A.S.S', b'S.M.A.S.M')
            for r in range(rows - 2):
                for c in range(cols - 2):
                    if any(re.match(p, grid[r:(r+3), c:(c+3)].tobytes()) for p in patterns):
                        count += 1
        return count
    elif day == 5:  # Print Queue
        rules, pages = puzzle_input.split('\n\n')
        total = 0
        for page_set in pages.splitlines():
            page_list = page_set.split(',')
            key = cmp_to_key(lambda a, b: 1 if f'{b}|{a}' in rules else -1 if f'{a}|{b}' in rules else 0)
            sorted_list = sorted(page_list, key=key)
            if (page_list == sorted_list) != (part == 2):
                middle_page = sorted_list[len(page_list) // 2]
                total += int(middle_page)
        return total
    elif day == 6:  # Guard Gallivant

        def get_guard_path(layout):
            approach_direction = {}  # which direction did we approach an obstacle from?
            obstacle_locations = np.array(np.where(layout == b'#')).T.tolist()
            guard_path = np.array(np.where(layout == b'^')).T.tolist()
            directions = np.array([[-1, 0], [0, 1], [1, 0], [0, -1]])  # up, right, down, left
            while True:
                new_pos = (guard_path[-1] + directions[0]).tolist()
                if new_pos in obstacle_locations:
                    pos_tuple = tuple(new_pos)
                    if approach_direction.get(pos_tuple, False) == directions[0].tolist():  # approaching from same direction as before
                        print(f'Hit obstacle at {new_pos} from direction {directions[0]}, loop detected')
                        return 'loop'
                    approach_direction[pos_tuple] = directions[0].tolist()
                    directions = np.roll(directions, -1, 0)  # turn right - i.e. next direction
                    # print(f'Hit obstacle at {new_pos} from direction {directions[-1]}, turning to {directions[0]}')
                elif 0 in new_pos or new_pos[0] >= rows or new_pos[1] >= cols:
                    print('Left maze at', new_pos)
                    break
                else:
                    guard_path += [new_pos]
                    layout[*new_pos] = 'X'
                text = layout.tobytes()
                # print(go_up * (rows + 1),
                #       b'\n'.join(text[i:i + cols] for i in range(0, rows * cols, cols)).decode('utf-8'), sep='')
                # print(len({tuple(pos) for pos in guard_path}))
                # sleep(0.1)
            return guard_path

        original_path = get_guard_path(original_layout.copy())
        unique_path_positions = {tuple(pos) for pos in original_path}
        if part == 1:
            return len(unique_path_positions)

        # try to make guard go in a loop by introducing one new obstacle somewhere on their path
        possible_obstacle_positions = 0
        unique_path_positions.remove(tuple(original_path[0]))  # remove starting position - can't put a new obstacle there
        for i, new_obstacle_pos in enumerate(unique_path_positions):
            print(f'Placing new obstacle at {new_obstacle_pos}, iteration {i} of {len(unique_path_positions)}')
            new_layout = original_layout.copy()
            new_layout[*new_obstacle_pos] = '#'
            if get_guard_path(new_layout) == 'loop':
                possible_obstacle_positions += 1
        return possible_obstacle_positions  # actually was 1 too small for part 2
    elif day == 7:  # Bridge Repair
        total_calibration_result = 0

        def concatenate(a, b):
            return int(f'{a}{b}')

        for line in puzzle_input:
            test_value, numbers = line.split(': ')
            test_value = int(test_value)
            numbers = [int(n) for n in numbers.split(' ')]
            print(numbers)
            n_operators = part + 1
            n_combos = n_operators ** (len(numbers) - 1)  # no of combos is 2^(n-1) where n is no of operators
            # print(n_combos)
            digits = len(np.base_repr(n_combos - 1, n_operators))
            # print(digits)
            for i in range(n_combos):
                combo_id = np.base_repr(i, n_operators)
                combo_id = '0' * (digits - len(combo_id)) + combo_id
                # print(combo_id)
                for move_to, o in enumerate(combo_id):
                    operator = add if o == '0' else mul if o == '1' else concatenate
                    result = operator(numbers[0] if move_to == 0 else result, numbers[move_to + 1])
                if result == test_value:
                    total_calibration_result += result
                    break
        return total_calibration_result
    elif day == 8:  # Resonant Collinearity
        freqs = set('\n'.join(puzzle_input))
        freqs.remove('\n')
        freqs.remove('.')
        antinode_locs = set()
        antinode_map = original_layout.copy()
        for freq in freqs:
            antenna_locs = np.array(np.where(original_layout == freq.encode('utf-8'))).T
            print(freq, antenna_locs)
            for i in range(len(antenna_locs) - 1):
                for move_to in range(i + 1, len(antenna_locs)):
                    separation = antenna_locs[move_to] - antenna_locs[i]
                    for k in (-1, 2) if part == 1 else range(-rows, rows + 1):
                        antinode_loc = antenna_locs[i] + k * separation
                        if 0 <= antinode_loc[0] < rows and 0 <= antinode_loc[1] < cols:
                            print(antinode_loc)
                            antinode_map[*antinode_loc] = '#'
                            antinode_locs.add(tuple(antinode_loc))
        text = antinode_map.tobytes()
        print(b'\n'.join(text[i:i + cols] for i in range(0, rows * cols, cols)).decode('utf-8'))
        return len(antinode_locs)
    elif day == 9:  # Disk Fragmenter
        fs_map = []
        file = True
        file_id = 0
        puzzle_input += '0'
        fs_map_2 = [[i // 2, int(puzzle_input[i]), int(puzzle_input[i + 1])] for i in range(0, len(puzzle_input), 2)]
        print(fs_map_2)
        for block_length in puzzle_input:
            fs_map += [file_id if file else '.'] * int(block_length)
            file = not file
            if file:
                file_id += 1
        # print(''.join('X' if isinstance(block, int) else block for block in fs_map))
        if part == 1:
            for i in range(len(fs_map) - 1, 0, -1):
                block = fs_map[i]
                if block == '.':
                    continue
                fs_map[fs_map.index('.')] = block
                fs_map[i] = '.'
                # print(''.join('X' if isinstance(block, int) else block for block in fs_map))

                if fs_map.index('.') >= i:
                    break
            return sum(i * file_id for i, file_id in enumerate(fs_map) if file_id != '.')
        else:
            i = -1
            moved_blocks = []
            while i > -len(fs_map_2):
                block_id, block_len, free_after = fs_map_2[i]
                if block_id in moved_blocks:  # don't move twice
                    i -= 1
                    continue
                for move_to, (bid, _, free_after_move_to) in enumerate(fs_map_2[:i - 1]):
                    if free_after_move_to < block_len:  # not enough space after
                        continue
                    print(f'Move {block_id} to {move_to}, goes after {fs_map_2[move_to]}')
                    fs_map_2[move_to][2] = 0  # no free space after
                    fs_map_2.insert(move_to + 1, [block_id, block_len, free_after_move_to - block_len])
                    fs_map_2[i - 1][2] += block_len + free_after  # more space after next-leftmost block
                    fs_map_2.pop(i)
                    moved_blocks.append(block_id)
                    break
                else:  # no blocks with enough space after
                    print(f"Can't move {block_id}")
                    i -= 1
            print(''.join(
                chr(48 + block_id) * block_len + '.' * free_after for block_id, block_len, free_after in fs_map_2))
            checksum = 0
            i = 0
            for file_id, block_len, free_after in fs_map_2:
                checksum += sum((i + j) * file_id for j in range(block_len))
                i += block_len + free_after
            return checksum
    elif day == 10:  # Hoof It
        # don't need a grid for this one
        puzzle_input = ''.join(puzzle_input).encode('utf-8')  # chars are easier to deal with here
        start = 0
        score_sum = 0
        while True:
            start = puzzle_input.find(48, start + 1)  # i.e. 0
            if start == -1:
                break
            path = [start]
            path_nodes = [Node(0)]
            score = 0
            i = 0
            while i < len(path):
                pos = path[i]
                height = puzzle_input[pos] - 48
                if height == 9:  # i.e. a peak
                    score += 1
                else:
                    for delta in (-cols, -1, 1, cols):  # can we climb from here?
                        new_pos = pos + delta
                        if 0 <= new_pos < len(puzzle_input) and puzzle_input[new_pos] - 48 == height + 1:
                            # if not done_one_pass:  # first pass: figure which nodes are visited more than once
                            if new_pos not in path:
                                new_node = Node(height + 1)
                                path_nodes.append(new_node)
                                path_nodes[i].can_move_to(new_node)
                                path.append(new_pos)
                            else:
                                path_nodes[i].can_move_to(path_nodes[path.index(new_pos)])
                i += 1
            flat_map = ''.join(chr(puzzle_input[i]) if i in path else '.' for i in range(max(path) + 1))
            flat_map = flat_map.replace('.' * cols, '')
            # print('\n'.join(flat_map[i:i + cols] for i in range(0, len(flat_map), cols)))
            # print(path)
            # print([puzzle_input[step] - 48 for step in path])
            # print(visits)
            rating = path_nodes[0].count_routes()
            print(rating)
            print(f'{start=} {score=} {rating=}')
            score_sum += (score if part == 1 else rating)
        return score_sum
    elif day == 11:  # Plutonian Pebbles
        stones = Counter(int(s) for s in puzzle_input.split(' '))
        blink_transform = {}
        for i in range(25 if part == 1 else 75):
            new_stones = Counter()
            for stone, count in stones.items():
                str_rep = str(stone)
                len_str = len(str_rep)
                if stone in blink_transform:
                    replacement = blink_transform[stone]
                else:
                    replacement = (1, ) if stone == 0 else \
                       (int(str_rep[len_str // 2:]), int(str_rep[:len_str // 2])) if len_str % 2 == 0 else \
                       (stone * 2024, )
                    blink_transform[stone] = replacement
                for new in replacement:
                    new_stones[new] += count
            stones = new_stones
            print(i, stones.total())
        return stones.total()
    elif day == 12:  # Garden Groups
        total_price = 0
        # find contiguous regions
        # puzzle_input.insert(0, puzzle_input[0])
        # puzzle_input.append(puzzle_input[-1])
        # for i in range(len(puzzle_input)):
        #     puzzle_input[i] = puzzle_input[i][0] + puzzle_input[i] + puzzle_input[i][-1]
        # puzzle_input[0] = '.' + puzzle_input[0][1:-2] + '.'
        # puzzle_input[-1] = '.' + puzzle_input[-1][1:-2] + '.'
        # cols += 2

        puzzle_input = ''.join(puzzle_input)
        regions = defaultdict(list)
        plots_used = set()
        for i, plot in enumerate(puzzle_input[1:(-cols-2)]):
            if i in plots_used:
                continue
            this_region = [i]
            plots_used.add(i)
            fence_around = Counter()
            perimeter = 0
            corners = 0
            j = 0
            while j < len(this_region):
                corner_check = set()
                pos = this_region[j]
                for delta in (-cols, -1, 1, cols):  # check neighbours
                    new_pos = pos + delta
                    wrapped = abs(delta) == 1 and pos // cols != new_pos // cols
                    if 0 <= new_pos < len(puzzle_input) and not wrapped and puzzle_input[new_pos] == plot:
                        plots_used.add(new_pos)
                        if new_pos not in this_region:
                            this_region.append(new_pos)
                    else:  # other plot or edge: need a fence
                        fence_around[new_pos] += 1
                        perimeter += 1
                        corner_check.add(delta)
                # corners += sum(s <= corner_check for s in ({-cols, -1}, {-cols, 1}, {cols, -1}, {cols, 1}))
                for delta in (-cols - 1, -cols + 1, cols - 1, cols + 1):  # corner test: diagonal neighbours
                    new_pos = pos + delta
                    if not 0 <= new_pos < len(puzzle_input) or puzzle_input[new_pos] != plot:
                        corners += 1
                j += 1
            print(plot, len(this_region), perimeter, corners)  # , sorted(this_region))
            regions[plot].append(i)
            total_price += len(this_region) * perimeter
        # get area of each
        # perimeter = area x 4 - (number of neighbour pairs) x 2
        return total_price

if __name__ == '__main__':
    test_input = '''RRRRIICCFF
RRRRIICCCF
VVRRRCCFFF
VVRCCCJFFF
VVVVCJJCFE
VVIVCCJJEE
VVIIICJJEE
MIIIIIJJEE
MIIISIJEEE
MMMISSJEEE
'''

    test_input = '''OOOOO
OXOXO
OOOOO
OXOXO
OOOOO
'''
    print(puzzle_2024(12, 2, test_input=test_input))
    # print('hello\n' * 10, end='')
    # sleep(1)
    # print(go_up * 10, 'goodbye\n' * 10, sep='')
