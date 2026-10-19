"""In-process model of Raft's rules.

This is the election, vote, append, and commit logic from the Raft paper,
run by direct calls instead of timers and a network. It exists so you can
see a majority, a rejected stale vote, and a committed log entry.
It is not a production Raft library.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Entry:
    term: int
    command: str


class RaftNode:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.current_term = 0
        self.voted_for: str | None = None
        self.log: list[Entry] = []
        self.commit_index = -1
        self.role = "follower"
        self.leader_id: str | None = None

    def last_index(self) -> int:
        return len(self.log) - 1

    def last_term(self) -> int:
        if not self.log:
            return 0
        return self.log[-1].term

    def request_vote(self, term: int, candidate_id: str, last_log_index: int, last_log_term: int) -> tuple[int, bool]:
        if term < self.current_term:
            return self.current_term, False
        if term > self.current_term:
            self._become_follower(term)
        log_ok = self._at_least_as_fresh(last_log_index, last_log_term)
        if log_ok and self.voted_for in (None, candidate_id):
            self.voted_for = candidate_id
            return self.current_term, True
        return self.current_term, False

    def append_entries(
        self,
        term: int,
        leader_id: str,
        prev_index: int,
        prev_term: int,
        entries: list[Entry],
        leader_commit: int,
    ) -> tuple[int, bool]:
        if term < self.current_term:
            return self.current_term, False
        if term > self.current_term:
            self._become_follower(term)
        self.role = "follower"
        self.leader_id = leader_id
        if prev_index >= 0:
            if prev_index >= len(self.log) or self.log[prev_index].term != prev_term:
                return self.current_term, False
        for offset, entry in enumerate(entries):
            index = prev_index + 1 + offset
            if index < len(self.log):
                if self.log[index].term != entry.term:
                    del self.log[index:]
                    self.log.append(entry)
            else:
                self.log.append(entry)
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log) - 1)
        return self.current_term, True

    def _at_least_as_fresh(self, last_log_index: int, last_log_term: int) -> bool:
        mine = self.last_term()
        if last_log_term != mine:
            return last_log_term > mine
        return last_log_index >= self.last_index()

    def _become_follower(self, term: int) -> None:
        self.current_term = term
        self.role = "follower"
        self.voted_for = None
        self.leader_id = None


class Cluster:
    def __init__(self, node_ids: list[str]) -> None:
        self.nodes = {node_id: RaftNode(node_id) for node_id in node_ids}

    def elect(self, candidate_id: str, voters: list[str] | None = None) -> bool:
        """voters limits who answers. A partition is a short voter list."""
        candidate = self.nodes[candidate_id]
        candidate.current_term += 1
        candidate.role = "candidate"
        candidate.voted_for = candidate_id
        candidate.leader_id = None
        votes = 1
        group = self.nodes if voters is None else {node_id: self.nodes[node_id] for node_id in voters}
        for other in group.values():
            if other is candidate:
                continue
            term, granted = other.request_vote(
                candidate.current_term,
                candidate_id,
                candidate.last_index(),
                candidate.last_term(),
            )
            if term > candidate.current_term:
                candidate._become_follower(term)
                return False
            if granted:
                votes += 1
        majority = len(self.nodes) // 2 + 1
        if votes >= majority:
            candidate.role = "leader"
            candidate.leader_id = candidate_id
            return True
        candidate.role = "follower"
        return False

    def propose(self, leader_id: str, command: str) -> int:
        leader = self.nodes[leader_id]
        if leader.role != "leader":
            raise RuntimeError("not the leader")
        leader.log.append(Entry(leader.current_term, command))
        self.replicate(leader_id)
        return leader.commit_index

    def replicate(self, leader_id: str) -> None:
        leader = self.nodes[leader_id]
        if leader.role != "leader":
            return
        matched: dict[str, int] = {leader.node_id: leader.last_index()}
        for other in self.nodes.values():
            if other is leader:
                continue
            prev = common_prefix(leader, other)
            entries = leader.log[prev + 1 :]
            prev_term = 0 if prev < 0 else leader.log[prev].term
            term, ok = other.append_entries(
                leader.current_term,
                leader.node_id,
                prev,
                prev_term,
                entries,
                leader.commit_index,
            )
            if term > leader.current_term:
                leader._become_follower(term)
                return
            if ok:
                matched[other.node_id] = other.last_index()
        self._advance_commit(leader, matched)
        for other in self.nodes.values():
            if other is leader or leader.role != "leader":
                continue
            prev = other.last_index()
            prev_term = 0 if prev < 0 else other.log[prev].term
            other.append_entries(leader.current_term, leader.node_id, prev, prev_term, [], leader.commit_index)

    def _advance_commit(self, leader: RaftNode, matched: dict[str, int]) -> None:
        majority = len(self.nodes) // 2 + 1
        for index in range(leader.last_index(), leader.commit_index, -1):
            if leader.log[index].term != leader.current_term:
                continue
            copies = sum(1 for reached in matched.values() if reached >= index)
            if copies >= majority:
                leader.commit_index = index
                return


def common_prefix(leader: RaftNode, follower: RaftNode) -> int:
    index = min(len(leader.log), len(follower.log)) - 1
    while index >= 0:
        if leader.log[index].term == follower.log[index].term:
            return index
        index -= 1
    return -1
