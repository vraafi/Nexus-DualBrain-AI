import logging

class FreelanceBranding:
    def __init__(self):
        self.platforms = ["upwork", "fiverr", "toptal"]

    def get_branding_strategy(self, platform):
        logging.info(f"Retrieving branding strategy for {platform}...")

        guidelines = {
            "upwork": {
                "persona": "Problem Solver Professional",
                "headline": "Backend Developer (Node.js/Express) | API Integration Specialist",
                "bio_focus": "Address client pain points (e.g., 'Apakah website Anda sering down?'). Do NOT write a CV.",
                "features": "Create 2 Specialized Profiles (e.g., Web Scraping, Bug Fixing).",
                "portfolio": "Use Case Studies with GTMetrix/Lighthouse Before & After screenshots, plus GitHub links.",
                "golden_rule": "Smile, clear background, good lighting for profile picture."
            },
            "fiverr": {
                 "persona": "Productized Service",
                 "seo": "Use specific keywords in Gig Title (e.g., 'I will fix PHP/WordPress fatal errors in 24 hours').",
                 "visuals": "Minimalist design (dark blue bg, bold white text) or screen recording explaining code.",
                 "pricing": "Clear Tiered Pricing (e.g., Basic = Fix 1 Bug).",
                 "golden_rule": "Smile, clear background, good lighting for profile picture."
            },
            "toptal": {
                 "persona": "Elite & Senior Engineer (Top 3%)",
                 "communication": "Business Acumen - explain choices based on cost/efficiency, act as Technical Consultant.",
                 "code_quality": "Strict adherence to SOLID principles, Design Patterns, and Unit Testing.",
                 "english": "Fluent professional English.",
                 "golden_rule": "Smile, clear background, good lighting for profile picture."
            }
        }

        strategy = guidelines.get(platform.lower())
        if strategy:
             logging.info(f"Strategy applied: {strategy['persona']}")
             return strategy
        else:
             logging.warning(f"Unknown platform: {platform}")
             return None
