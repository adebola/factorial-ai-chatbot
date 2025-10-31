"""
Basic Sentiment Analyzer using VADER

VADER (Valence Aware Dictionary and sEntiment Reasoner) is a rule-based
sentiment analysis tool that is:
- Fast (< 1ms per analysis)
- Free (no API costs)
- No ML models required
- Optimized for social media and short text

Perfect for detecting frustration in chat messages as a proxy for poor answers.
"""

from typing import Dict
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from app.core.logging_config import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class SentimentAnalyzer:
    """
    Analyze sentiment of chat messages using VADER.

    Sentiment is used as a proxy for answer quality:
    - Negative/Frustrated = Likely poor answer quality
    - Positive = Likely good answer quality
    - Neutral = Most common for informational queries
    """

    def __init__(self):
        """Initialize VADER sentiment analyzer"""
        if settings.ENABLE_BASIC_SENTIMENT:
            self.analyzer = SentimentIntensityAnalyzer()
            logger.info("VADER sentiment analyzer initialized")
        else:
            self.analyzer = None
            logger.info("Sentiment analysis disabled via config")

    def analyze(self, text: str) -> Dict[str, any]:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze (e.g., AI response content)

        Returns:
            Dictionary with:
            - label: 'positive', 'neutral', 'negative', or 'frustrated'
            - score: VADER compound score (-1 to +1)
            - scores: Individual scores (pos, neu, neg, compound)

        VADER Compound Score Interpretation:
        - >= 0.05: Positive
        - > -0.05 and < 0.05: Neutral
        - <= -0.05: Negative
        - <= -0.5: Frustrated (strong negative)
        """
        if not self.analyzer:
            return {
                "label": None,
                "score": None,
                "scores": None,
                "enabled": False
            }

        if not text or not text.strip():
            return {
                "label": "neutral",
                "score": 0.0,
                "scores": {"pos": 0.0, "neu": 1.0, "neg": 0.0, "compound": 0.0},
                "enabled": True
            }

        try:
            # Get VADER scores
            scores = self.analyzer.polarity_scores(text)
            compound = scores['compound']

            # Determine sentiment label
            if compound >= 0.05:
                label = "positive"
            elif compound <= -0.05:
                if compound <= -0.5:  # Strong negative = frustration
                    label = "frustrated"
                else:
                    label = "negative"
            else:
                label = "neutral"

            return {
                "label": label,
                "score": compound,
                "scores": scores,
                "enabled": True
            }

        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}", exc_info=True)
            return {
                "label": "neutral",
                "score": 0.0,
                "scores": None,
                "enabled": True,
                "error": str(e)
            }

    def is_frustrated(self, text: str, threshold: float = -0.5) -> bool:
        """
        Check if text indicates frustration.

        Useful for detecting users who are frustrated with poor answers.

        Args:
            text: Text to analyze
            threshold: Compound score threshold for frustration (default: -0.5)

        Returns:
            True if text indicates frustration
        """
        if not self.analyzer:
            return False

        result = self.analyze(text)
        return result["label"] == "frustrated" or (
            result["score"] is not None and result["score"] <= threshold
        )

    def analyze_conversation_tone(self, messages: list) -> Dict[str, any]:
        """
        Analyze overall tone of a conversation.

        Args:
            messages: List of message texts

        Returns:
            Dictionary with:
            - overall_sentiment: Average compound score
            - sentiment_trend: 'improving', 'declining', or 'stable'
            - frustration_count: Number of frustrated messages
        """
        if not self.analyzer or not messages:
            return {
                "overall_sentiment": 0.0,
                "sentiment_trend": "stable",
                "frustration_count": 0
            }

        scores = []
        frustration_count = 0

        for message in messages:
            result = self.analyze(message)
            if result["score"] is not None:
                scores.append(result["score"])
                if result["label"] == "frustrated":
                    frustration_count += 1

        if not scores:
            return {
                "overall_sentiment": 0.0,
                "sentiment_trend": "stable",
                "frustration_count": 0
            }

        # Calculate overall sentiment
        overall_sentiment = sum(scores) / len(scores)

        # Determine trend (compare first half vs second half)
        if len(scores) >= 4:
            mid = len(scores) // 2
            first_half_avg = sum(scores[:mid]) / mid
            second_half_avg = sum(scores[mid:]) / (len(scores) - mid)

            if second_half_avg > first_half_avg + 0.1:
                sentiment_trend = "improving"
            elif second_half_avg < first_half_avg - 0.1:
                sentiment_trend = "declining"
            else:
                sentiment_trend = "stable"
        else:
            sentiment_trend = "stable"

        return {
            "overall_sentiment": round(overall_sentiment, 3),
            "sentiment_trend": sentiment_trend,
            "frustration_count": frustration_count
        }


# Global sentiment analyzer instance
sentiment_analyzer = SentimentAnalyzer()
