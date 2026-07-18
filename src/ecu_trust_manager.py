class ECUTrustManager:
    def __init__(self) -> None:
        self.scores = {}

    def get_score(self, ecu_id: str) -> float:
        return self.scores.get(ecu_id, 1.0)

    def update(self, ecu_id: str, penalty: float = 0.0, reward: float = 0.0) -> float:
        score = self.get_score(ecu_id)
        score = max(0.0, min(1.0, score - penalty + reward))
        self.scores[ecu_id] = score
        return score

    def classify(self, ecu_id: str) -> str:
        score = self.get_score(ecu_id)
        if score >= 0.8:
            return "trusted"
        if score >= 0.5:
            return "monitor"
        if score >= 0.2:
            return "suspicious"
        return "blocked"
