"""Generate 49 synthetic student benchmark cases and reference evaluations."""

import hashlib
import json
from pathlib import Path

DEST = Path("/home/rosso/Projects/Parakh/benchmarks_student")
DEST.mkdir(parents=True, exist_ok=True)

# 10 Code cases
code_cases = [
    {
        "id": "STU-CODE-01",
        "family": "student-code-v1",
        "complexity": 1,
        "prompt": "Write a Python function `is_even(n: int) -> bool` that returns True if n is even and False otherwise.",
        "ref": "def is_even(n: int) -> bool:\n    return n % 2 == 0",
        "check_type": "python_exec",
        "check_code": "assert is_even(4) is True\nassert is_even(7) is False\nassert is_even(0) is True",
    },
    {
        "id": "STU-CODE-02",
        "family": "student-code-v1",
        "complexity": 1,
        "prompt": "Write a Python function `reverse_string(s: str) -> str` that reverses the given string.",
        "ref": "def reverse_string(s: str) -> str:\n    return s[::-1]",
        "check_type": "python_exec",
        "check_code": "assert reverse_string('karmi') == 'imrak'\nassert reverse_string('') == ''",
    },
    {
        "id": "STU-CODE-03",
        "family": "student-code-v1",
        "complexity": 2,
        "prompt": "Write a Python function `sum_of_squares(nums: list[int]) -> int` returning the sum of squares of elements in nums.",
        "ref": "def sum_of_squares(nums: list[int]) -> int:\n    return sum(x * x for x in nums)",
        "check_type": "python_exec",
        "check_code": "assert sum_of_squares([1, 2, 3]) == 14\nassert sum_of_squares([]) == 0",
    },
    {
        "id": "STU-CODE-04",
        "family": "student-code-v1",
        "complexity": 2,
        "prompt": "Write a Python function `count_vowels(text: str) -> int` counting vowels (a, e, i, o, u, case-insensitive) in text.",
        "ref": "def count_vowels(text: str) -> int:\n    return sum(1 for c in text.lower() if c in 'aeiou')",
        "check_type": "python_exec",
        "check_code": "assert count_vowels('Namaste India') == 6\nassert count_vowels('xyz') == 0",
    },
    {
        "id": "STU-CODE-05",
        "family": "student-code-v1",
        "complexity": 2,
        "prompt": "Write a Python function `find_max(nums: list[int]) -> int` that returns the largest number in a non-empty list.",
        "ref": "def find_max(nums: list[int]) -> int:\n    return max(nums)",
        "check_type": "python_exec",
        "check_code": "assert find_max([10, 42, 5, 99, 12]) == 99\nassert find_max([-5, -1]) == -1",
    },
    {
        "id": "STU-CODE-06",
        "family": "student-code-v1",
        "complexity": 3,
        "prompt": "Write a Python function `is_palindrome(s: str) -> bool` checking if an alphanumeric string is a palindrome, ignoring non-alphanumeric chars and case.",
        "ref": "def is_palindrome(s: str) -> bool:\n    clean = [c.lower() for c in s if c.isalnum()]\n    return clean == clean[::-1]",
        "check_type": "python_exec",
        "check_code": "assert is_palindrome('A man, a plan, a canal: Panama') is True\nassert is_palindrome('race a car') is False",
    },
    {
        "id": "STU-CODE-07",
        "family": "student-code-v1",
        "complexity": 3,
        "prompt": "Write a Python function `fibonacci(n: int) -> int` returning the n-th Fibonacci number (where fibonacci(0)=0, fibonacci(1)=1).",
        "ref": "def fibonacci(n: int) -> int:\n    if n <= 0:\n        return 0\n    elif n == 1:\n        return 1\n    a, b = 0, 1\n    for _ in range(2, n + 1):\n        a, b = b, a + b\n    return b",
        "check_type": "python_exec",
        "check_code": "assert fibonacci(0) == 0\nassert fibonacci(1) == 1\nassert fibonacci(7) == 13",
    },
    {
        "id": "STU-CODE-08",
        "family": "student-code-v1",
        "complexity": 3,
        "prompt": "Write a Python function `flatten_list(nested: list[list[int]]) -> list[int]` that flattens a 2D list into a 1D list.",
        "ref": "def flatten_list(nested: list[list[int]]) -> list[int]:\n    return [item for sub in nested for item in sub]",
        "check_type": "python_exec",
        "check_code": "assert flatten_list([[1, 2], [3, 4], [5]]) == [1, 2, 3, 4, 5]",
    },
    {
        "id": "STU-CODE-09",
        "family": "student-code-v1",
        "complexity": 4,
        "prompt": "Write a Python function `merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]` that merges overlapping intervals.",
        "ref": "def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:\n    if not intervals:\n        return []\n    sorted_i = sorted(intervals, key=lambda x: x[0])\n    merged = [sorted_i[0]]\n    for start, end in sorted_i[1:]:\n        prev_start, prev_end = merged[-1]\n        if start <= prev_end:\n            merged[-1] = (prev_start, max(prev_end, end))\n        else:\n            merged.append((start, end))\n    return merged",
        "check_type": "python_exec",
        "check_code": "assert merge_intervals([(1, 3), (2, 6), (8, 10), (15, 18)]) == [(1, 6), (8, 10), (15, 18)]",
    },
    {
        "id": "STU-CODE-10",
        "family": "student-code-v1",
        "complexity": 4,
        "prompt": "Write a Python function `two_sum(nums: list[int], target: int) -> tuple[int, int] | None` returning 0-based indices of two numbers that add up to target.",
        "ref": "def two_sum(nums: list[int], target: int) -> tuple[int, int] | None:\n    seen = {}\n    for i, n in enumerate(nums):\n        comp = target - n\n        if comp in seen:\n            return (seen[comp], i)\n        seen[n] = i\n    return None",
        "check_type": "python_exec",
        "check_code": "assert two_sum([2, 7, 11, 15], 9) == (0, 1)\nassert two_sum([3, 2, 4], 6) == (1, 2)",
    },
]

# 10 Maths cases
maths_cases = [
    {
        "id": "STU-MATH-01",
        "family": "student-math-v1",
        "complexity": 1,
        "prompt": "What is the perimeter of a rectangle with length 14 cm and breadth 9 cm? Return only the numerical value in cm.",
        "ref": "46",
        "check_type": "exact_numeric",
        "expected": 46.0,
    },
    {
        "id": "STU-MATH-02",
        "family": "student-math-v1",
        "complexity": 1,
        "prompt": "A student scores 72 out of 80 in Mathematics. What is the percentage scored? Return only the numerical percentage value.",
        "ref": "90",
        "check_type": "exact_numeric",
        "expected": 90.0,
    },
    {
        "id": "STU-MATH-03",
        "family": "student-math-v1",
        "complexity": 2,
        "prompt": "If 5 pens cost 75 INR, what is the cost of 12 pens at the same rate in INR? Return only the number.",
        "ref": "180",
        "check_type": "exact_numeric",
        "expected": 180.0,
    },
    {
        "id": "STU-MATH-04",
        "family": "student-math-v1",
        "complexity": 2,
        "prompt": "Solve for x in the linear equation: 3x - 7 = 29. Return only the value of x.",
        "ref": "12",
        "check_type": "exact_numeric",
        "expected": 12.0,
    },
    {
        "id": "STU-MATH-05",
        "family": "student-math-v1",
        "complexity": 2,
        "prompt": "Find the simple interest on a principal of 5000 INR at an annual rate of 6% for 3 years. Return only the interest in INR.",
        "ref": "900",
        "check_type": "exact_numeric",
        "expected": 900.0,
    },
    {
        "id": "STU-MATH-06",
        "family": "student-math-v1",
        "complexity": 3,
        "prompt": "A train 150 meters long crosses a pole in 9 seconds. What is its speed in km/h? Return only the numerical value.",
        "ref": "60",
        "check_type": "exact_numeric",
        "expected": 60.0,
    },
    {
        "id": "STU-MATH-07",
        "family": "student-math-v1",
        "complexity": 3,
        "prompt": "What is the area of a right-angled triangle with base 15 cm and hypotenuse 17 cm in cm²? Return only the number.",
        "ref": "60",
        "check_type": "exact_numeric",
        "expected": 60.0,
    },
    {
        "id": "STU-MATH-08",
        "family": "student-math-v1",
        "complexity": 3,
        "prompt": "Find the roots of the quadratic equation x^2 - 11x + 30 = 0. What is the sum of the roots? Return only the number.",
        "ref": "11",
        "check_type": "exact_numeric",
        "expected": 11.0,
    },
    {
        "id": "STU-MATH-09",
        "family": "student-math-v1",
        "complexity": 4,
        "prompt": "In how many distinct ways can the letters of the word 'BHARAT' be arranged? Return only the integer count.",
        "ref": "360",
        "check_type": "exact_numeric",
        "expected": 360.0,
    },
    {
        "id": "STU-MATH-10",
        "family": "student-math-v1",
        "complexity": 4,
        "prompt": "Two dice are rolled simultaneously. What is the probability of getting a sum equal to 8? Return as a simplified fraction string like 'a/b'.",
        "ref": "5/36",
        "check_type": "exact_string",
        "expected": "5/36",
    },
]

# 10 Study cases
study_cases = [
    {
        "id": "STU-STUDY-01",
        "family": "student-study-v1",
        "complexity": 1,
        "prompt": "Explain the process of photosynthesis in plants in 2-3 sentences. Mention the role of chlorophyll and sunlight.",
        "ref": "Photosynthesis is the process by which green plants synthesize glucose from carbon dioxide and water using sunlight absorbed by chlorophyll. Oxygen is released as a byproduct during this reaction.",
        "check_type": "keywords",
        "keywords": ["photosynthesis", "chlorophyll", "sunlight", "carbon dioxide", "oxygen"],
    },
    {
        "id": "STU-STUDY-02",
        "family": "student-study-v1",
        "complexity": 1,
        "prompt": "State Newton's First Law of Motion and explain the concept of inertia with a short example.",
        "ref": "Newton's First Law states that an object remains at rest or in uniform motion unless acted upon by an external unbalanced force. This tendency to resist change in motion is called inertia, such as when passengers lurch forward when a bus brakes suddenly.",
        "check_type": "keywords",
        "keywords": ["inertia", "rest", "motion", "force"],
    },
    {
        "id": "STU-STUDY-03",
        "family": "student-study-v1",
        "complexity": 2,
        "prompt": "What is the difference between kinetic energy and potential energy? Provide one clear example of each.",
        "ref": "Kinetic energy is the energy possessed by an object due to its motion, like a moving car. Potential energy is stored energy due to an object's position or state, such as water stored behind a dam.",
        "check_type": "keywords",
        "keywords": ["kinetic", "potential", "motion", "energy"],
    },
    {
        "id": "STU-STUDY-04",
        "family": "student-study-v1",
        "complexity": 2,
        "prompt": "Explain the water cycle. Briefly describe evaporation, condensation, and precipitation.",
        "ref": "The water cycle describes continuous water movement on Earth. Water heats and undergoes evaporation into vapor, cools to form clouds via condensation, and falls back to Earth as precipitation.",
        "check_type": "keywords",
        "keywords": ["evaporation", "condensation", "precipitation", "clouds"],
    },
    {
        "id": "STU-STUDY-05",
        "family": "student-study-v1",
        "complexity": 2,
        "prompt": "What are the primary differences between plant cells and animal cells regarding cell wall and chloroplasts?",
        "ref": "Plant cells possess a rigid cellulose cell wall and chloroplasts for photosynthesis, whereas animal cells lack both cell walls and chloroplasts and have only a flexible cell membrane.",
        "check_type": "keywords",
        "keywords": ["cell wall", "chloroplasts", "plant", "animal"],
    },
    {
        "id": "STU-STUDY-06",
        "family": "student-study-v1",
        "complexity": 3,
        "prompt": "Explain Ohm's Law in electric circuits. State the mathematical relationship between voltage, current, and resistance.",
        "ref": "Ohm's Law states that current flowing through a conductor between two points is directly proportional to voltage and inversely proportional to resistance: V = I * R.",
        "check_type": "keywords",
        "keywords": ["voltage", "current", "resistance", "ohm"],
    },
    {
        "id": "STU-STUDY-07",
        "family": "student-study-v1",
        "complexity": 3,
        "prompt": "Describe the function of hemoglobin in human blood and how oxygen transport occurs.",
        "ref": "Hemoglobin is an iron-rich protein in red blood cells that binds reversibly to oxygen in the lungs to form oxyhemoglobin, transporting oxygen to tissues throughout the body.",
        "check_type": "keywords",
        "keywords": ["hemoglobin", "oxygen", "red blood cells", "lungs"],
    },
    {
        "id": "STU-STUDY-08",
        "family": "student-study-v1",
        "complexity": 3,
        "prompt": "Explain the difference between renewable and non-renewable energy sources with two examples of each.",
        "ref": "Renewable energy comes from inexhaustible natural sources like solar and wind power. Non-renewable energy comes from finite sources that deplete over time, such as coal and petroleum.",
        "check_type": "keywords",
        "keywords": ["renewable", "solar", "wind", "coal", "petroleum"],
    },
    {
        "id": "STU-STUDY-09",
        "family": "student-study-v1",
        "complexity": 4,
        "prompt": "Explain how enzymes function as biological catalysts, mentioning activation energy and the active site.",
        "ref": "Enzymes are protein catalysts that speed up chemical reactions by lowering the activation energy required. Substrate molecules bind specifically to the enzyme's active site forming an enzyme-substrate complex.",
        "check_type": "keywords",
        "keywords": ["enzymes", "catalyst", "activation energy", "active site", "substrate"],
    },
    {
        "id": "STU-STUDY-10",
        "family": "student-study-v1",
        "complexity": 4,
        "prompt": "Discuss the greenhouse effect, greenhouse gases like carbon dioxide and methane, and their impact on global climate change.",
        "ref": "The greenhouse effect is the trapping of heat in Earth's atmosphere by gases such as carbon dioxide and methane, preventing thermal radiation from escaping into space and causing global warming.",
        "check_type": "keywords",
        "keywords": ["greenhouse", "carbon dioxide", "methane", "atmosphere", "warming"],
    },
]

# 8 Hindi cases
hindi_cases = [
    {
        "id": "STU-HIN-01",
        "family": "student-hindi-v1",
        "complexity": 1,
        "prompt": "प्रकाश संश्लेषण क्या है? दो वाक्यों में सरल हिंदी में समझाइए। उत्तर केवल देवनागरी लिपि में दें।",
        "ref": "प्रकाश संश्लेषण वह प्रक्रिया है जिसके द्वारा हरे पौधे सूर्य के प्रकाश और क्लोरोफिल की सहायता से अपना भोजन बनाते हैं। इस प्रक्रिया में पौधे कार्बन डाइऑक्साइड लेते हैं और ऑक्सीजन छोड़ते हैं।",
        "check_type": "devanagari",
        "keywords": ["पौधे", "प्रकाश", "भोजन", "ऑक्सीजन"],
    },
    {
        "id": "STU-HIN-02",
        "family": "student-hindi-v1",
        "complexity": 1,
        "prompt": "जल संरक्षण के दो मुख्य उपाय हिंदी में संक्षेप में लिखिए। उत्तर केवल देवनागरी लिपि में दें।",
        "ref": "जल संरक्षण के लिए वर्षा जल संचयन करना चाहिए और दैनिक कार्यों में पानी का व्यर्थ बहाव रोकना चाहिए।",
        "check_type": "devanagari",
        "keywords": ["जल", "संरक्षण", "पानी"],
    },
    {
        "id": "STU-HIN-03",
        "family": "student-hindi-v1",
        "complexity": 2,
        "prompt": "सौर मंडल का सबसे बड़ा ग्रह कौन सा है और उसका एक मुख्य लक्षण क्या है? उत्तर केवल देवनागरी लिपि में दें।",
        "ref": "सौर मंडल का सबसे बड़ा ग्रह बृहस्पति है। यह एक गैसीय दानव है और इसमें विशाल लाल धब्बा तूफान मौजूद है।",
        "check_type": "devanagari",
        "keywords": ["बृहस्पति", "ग्रह", "सौर मंडल"],
    },
    {
        "id": "STU-HIN-04",
        "family": "student-hindi-v1",
        "complexity": 2,
        "prompt": "संतुलित आहार किसे कहते हैं? इसके दो प्रमुख घटकों के नाम लिखिए। उत्तर केवल देवनागरी लिपि में दें।",
        "ref": "संतुलित आहार वह आहार है जिसमें शरीर की वृद्धि और स्वास्थ्य के लिए सभी आवश्यक पोषक तत्व उचित मात्रा में हों, जैसे प्रोटीन और कार्बोहाइड्रेट।",
        "check_type": "devanagari",
        "keywords": ["संतुलित आहार", "पोषक तत्व", "प्रोटीन"],
    },
    {
        "id": "STU-HIN-05",
        "family": "student-hindi-v1",
        "complexity": 3,
        "prompt": "पर्यावरण प्रदूषण रोकने के तीन महत्वपूर्ण उपाय समझाइए। उत्तर केवल देवनागरी लिपि में दें।",
        "ref": "पर्यावरण प्रदूषण रोकने के लिए वृक्षारोपण बढ़ाना चाहिए, प्लास्टिक का उपयोग बंद करना चाहिए और सार्वजनिक वाहनों का अधिक उपयोग करना चाहिए।",
        "check_type": "devanagari",
        "keywords": ["पर्यावरण", "प्रदूषण", "वृक्षारोपण"],
    },
    {
        "id": "STU-HIN-06",
        "family": "student-hindi-v1",
        "complexity": 3,
        "prompt": "कंप्यूटर में सॉफ्टवेयर और हार्डवेयर का क्या अंतर है? उत्तर केवल देवनागरी लिपि में दें।",
        "ref": "हार्डवेयर कंप्यूटर के भौतिक भाग होते हैं जिन्हें हम छू सकते हैं जैसे कीबोर्ड और मॉनिटर। सॉफ्टवेयर वे प्रोग्राम और निर्देश होते हैं जो कंप्यूटर को कार्य करने का निर्देश देते हैं।",
        "check_type": "devanagari",
        "keywords": ["हार्डवेयर", "सॉफ्टवेयर", "कंप्यूटर"],
    },
    {
        "id": "STU-HIN-07",
        "family": "student-hindi-v1",
        "complexity": 4,
        "prompt": "भारतीय संविधान की प्रस्तावना में निहित मुख्य आदर्शों (न्याय, स्वतंत्रता, समानता, बंधुता) का संक्षेप में वर्णन कीजिए। उत्तर केवल देवनागरी में दें।",
        "ref": "भारतीय संविधान की प्रस्तावना भारत को एक संप्रभु, समाजवादी, धर्मनिरपेक्ष, लोकतांत्रिक गणराज्य घोषित करती है और सभी नागरिकों के लिए सामाजिक, आर्थिक व राजनीतिक न्याय, स्वतंत्रता, समानता और बंधुता सुनिश्चित करती है।",
        "check_type": "devanagari",
        "keywords": ["संविधान", "प्रस्तावना", "न्याय", "समानता", "स्वतंत्रता"],
    },
    {
        "id": "STU-HIN-08",
        "family": "student-hindi-v1",
        "complexity": 4,
        "prompt": "ओजोन परत का क्या महत्व है और यह पृथ्वी पर जीवन की रक्षा कैसे करती है? उत्तर केवल देवनागरी में दें।",
        "ref": "ओजोन परत समताप मंडल में स्थित है और यह सूर्य से आने वाली हानिकारक पराबैंगनी किरणों को अवशोषित करके पृथ्वी पर जीवन की रक्षा करती है।",
        "check_type": "devanagari",
        "keywords": ["ओजोन परत", "पराबैंगनी", "पृथ्वी", "रक्षा"],
    },
]

# 8 Mixed Hindi-English cases
mixed_cases = [
    {
        "id": "STU-MIX-01",
        "family": "student-mixed-v1",
        "complexity": 1,
        "prompt": "Physics me velocity aur speed me kya difference hota hai? Hinglish me explain karo.",
        "ref": "Speed ek scalar quantity hai jisme sirf magnitude hota hai, jabki velocity ek vector quantity hai jisme magnitude ke saath direction bhi hoti hai.",
        "check_type": "mixed_script",
        "keywords": ["speed", "velocity", "scalar", "vector", "magnitude"],
    },
    {
        "id": "STU-MIX-02",
        "family": "student-mixed-v1",
        "complexity": 1,
        "prompt": "Computer me RAM aur ROM ka kya difference hai? Short me Hinglish me samjhao.",
        "ref": "RAM temporary memory hoti hai jo volatile hai aur power off hone par data erase ho jata hai. ROM permanent memory hai jisme boot instructions store hote hain.",
        "check_type": "mixed_script",
        "keywords": ["ram", "rom", "volatile", "memory", "data"],
    },
    {
        "id": "STU-MIX-03",
        "family": "student-mixed-v1",
        "complexity": 2,
        "prompt": "Chemistry me acids aur bases ke taste aur litmus paper test ka difference Hinglish me batao.",
        "ref": "Acids taste me sour hote hain aur blue litmus ko red kar dete hain. Bases taste me bitter hote hain aur red litmus ko blue kar dete hain.",
        "check_type": "mixed_script",
        "keywords": ["acid", "base", "litmus", "red", "blue"],
    },
    {
        "id": "STU-MIX-04",
        "family": "student-mixed-v1",
        "complexity": 2,
        "prompt": "Exam preparation ke liye time management ke 2 useful tips Hinglish me suggest karo.",
        "ref": "Time management ke liye daily study routine ka realistic schedule banao jisme regular breaks hon, aur difficult topics ko subah fresh mind se pehle cover karo.",
        "check_type": "mixed_script",
        "keywords": ["study", "schedule", "routine", "time"],
    },
    {
        "id": "STU-MIX-05",
        "family": "student-mixed-v1",
        "complexity": 3,
        "prompt": "Biology me mitosis aur meiosis cell division ka basic difference Hinglish me explain karo.",
        "ref": "Mitosis me ek parent cell se 2 identical diploid daughter cells banti hain growth ke liye. Meiosis me 4 haploid gamete cells banti hain reproduction ke liye.",
        "check_type": "mixed_script",
        "keywords": ["mitosis", "meiosis", "cell", "diploid", "haploid"],
    },
    {
        "id": "STU-MIX-06",
        "family": "student-mixed-v1",
        "complexity": 3,
        "prompt": "Economics me inflation ka common person ke daily budget par kya impact hota hai? Hinglish me samjhao.",
        "ref": "Inflation ka matlab hai general price level badhna, jisse currency ki purchasing power kam ho jati hai aur daily budget affect hota hai kyunki items expensive ho jate hain.",
        "check_type": "mixed_script",
        "keywords": ["inflation", "price", "budget", "purchasing power"],
    },
    {
        "id": "STU-MIX-07",
        "family": "student-mixed-v1",
        "complexity": 4,
        "prompt": "Machine Learning me Supervised aur Unsupervised learning ka core difference with example Hinglish me clarify karo.",
        "ref": "Supervised learning me model labeled data par train hota hai jaise spam detection. Unsupervised learning me unlabeled data ke patterns aur clusters find kiye jate hain jaise customer segmentation.",
        "check_type": "mixed_script",
        "keywords": ["supervised", "unsupervised", "labeled", "data", "train"],
    },
    {
        "id": "STU-MIX-08",
        "family": "student-mixed-v1",
        "complexity": 4,
        "prompt": "Internet security me Phishing attacks kya hote hain aur inse kaise protect karein? Hinglish me guide karo.",
        "ref": "Phishing ek cyber attack hai jisme account security compromise karke fake emails ya websites ke through users se passwords churaye jate hain. Suspicious links par click na karein aur 2FA enable karein.",
        "check_type": "mixed_script",
        "keywords": ["phishing", "attack", "password", "security", "links"],
    },
]

# Synthetic long-context passage (>= 6000 characters) for STU-SUM-01
long_synthetic_text_blocks = [
    """CHAPTER 1: THE FOUNDING OF THE UDAYAGIRI SOLAR AND ASTRONOMICAL RESEARCH INITIATIVE (1974)
In the autumn of 1974, a consortium of Indian scientists, meteorologists, and educational innovators established the Udayagiri High-Altitude Solar and Astronomical Research Facility (UHSARF) atop the Vindhyachal plateau in Central India. Spearheaded by Dr. Anandamurthy Kulkarni and Professor Sneha Deshmukh, the facility was designed to address three distinct scientific imperatives: long-term monitoring of solar irradiance variations, documenting upper atmospheric turbulence patterns in the tropics, and providing high-resolution observational curricula for undergraduate physics students across rural universities.

The geographical coordinates of the primary observatory dome were fixed at 23.4128 degrees North latitude and 77.7214 degrees East longitude, at an elevation of 742 meters above mean sea level. This specific plateau was selected after an exhaustive 18-month micro-climate assessment, which revealed an average of 268 cloud-free nights per calendar year, remarkably low ambient humidity during the winter months, and an optical seeing parameter consistently below 1.2 arcseconds.

The initial capital funding for UHSARF was sanctioned under Special Grant Ref-IN-74-902, totaling 18.4 million Indian Rupees, co-financed by the Department of Science and Technology and the University Grants Commission. Construction commenced on November 12, 1974, utilizing locally quarried sandstone for the thermal insulation of the instrument vaults and reinforced granite pilings embedded sixteen meters into the basalt bedrock to eliminate seismic ground vibrations caused by nearby railway corridors.""",

    """CHAPTER 2: INSTRUMENTATION AND APERTURE CONFIGURATIONS
Between 1976 and 1982, three primary optical telescope instruments were commissioned at the facility:
1. The Surya-70 Solar Spectrograph: A 70-centimeter coelostat feeding an underground Littrow spectrograph with a 12-meter focal length. This instrument recorded daily photographic plates of the solar chromosphere in hydrogen-alpha (656.3 nm) and calcium-K (393.4 nm) wavelengths. The primary optical flat was coated with evaporated aluminum with a magnesium fluoride protective overcoat, yielding a peak reflectance of 91.5 percent across the visible spectrum.

2. The Vindhya-120 Cassegrain Reflector: A 1.2-meter parabolic primary mirror configured with a focal ratio of f/8 for stellar spectroscopy and f/15 for narrow-field planetary astrometry. The primary mirror was fabricated from Schott Zerodur glass-ceramic, exhibiting a thermal expansion coefficient of less than 0.05 x 10^-6 per Kelvin, ensuring optical stability during rapid midnight temperature shifts.

3. The Rohini Wide-Field Schmidt Camera: Equipped with an 85-centimeter corrector plate and a 115-centimeter spherical mirror, designed specifically for rapid survey photographic tracking of near-Earth asteroids and transient cometary apparitions. Over its operational lifespan, the Rohini camera exposed 4,218 glass photographic plates, identifying 14 previously uncatalogued minor planet candidates between 1979 and 1991.

Data storage throughout the analogue era relied on temperature-regulated archives maintained strictly at 18 degrees Celsius and 45 percent relative humidity. More than 12,000 physical photographic glass plates were cataloged under the archival accession code UHS-ARC-VIS.""",

    """CHAPTER 3: EDUCATIONAL OUTREACH AND CURRICULUM DISSEMINATION
A founding principle of UHSARF was the democratization of modern astronomical education. Beginning in January 1978, the observatory inaugurated the Winter Scholar Fellowship Program (WSFP). Every December, sixty post-graduate students selected from state colleges across Rajasthan, Madhya Pradesh, Maharashtra, and Uttar Pradesh attended an intensive four-week residential workshop.

The curriculum comprised four distinct modules:
- Module A (Optical Principles): Alignment of spherical and parabolic optical surfaces, diffraction gratings, slit aberrations, and photometric error analysis.
- Module B (Computational Astrometry): Orbital mechanics calculation using hand calculators and early mainframe punched cards (specifically an ECIL TDC-316 computing unit installed in 1980).
- Module C (Solar Flare Dynamics): Tracking sunspot groups (Zurich classification classes A through F) and estimating magnetic flux densities from Zeeman splitting records.
- Module D (Atmospheric Extinction): Measuring atmospheric optical depth using multi-band photoelectric photometers.

Between 1978 and 1998, a total of 1,264 students graduated from WSFP, of whom 312 subsequently completed doctoral dissertations in astrophysics and remote sensing disciplines. Field alumni notably contributed to the development of early Indian space payloads, meteorological satellite sensors, and high-altitude infrared instrumentation.""",

    """CHAPTER 4: MODERNIZATION, DIGITAL PHOTOMETRY, AND RENEWABLE CONVERSION
As digital solid-state detectors superseded photographic emulsion in the late 1990s, the observatory initiated Project Navikaran (1999-2004). Under the direction of Chief Systems Engineer Dr. Vikramaditya Joshi, the Cassegrain focus of the Vindhya-120 was retrofitted with a cryogenically cooled 4096 x 4096 pixel charge-coupled device (CCD) sensor operating at minus 110 degrees Celsius using closed-cycle liquid nitrogen refrigeration.

Simultaneously, the facility underwent an off-grid clean energy transformation. In 2003, a 150-kilowatt rooftop solar photovoltaic microgrid with lead-acid battery backup was integrated across the administrative building and workshop roofs. This microgrid reduced grid brownout events from an average of 42 interruptions per year to zero, stabilizing cryogenic detectors and optical tracking servomotors.

In 2018, the facility marked its transition into autonomous robotic operations, linking its solar monitoring feed to automated alert networks for space-weather forecasting and coronal mass ejection trajectory modeling. The historical plate collection was fully digitized between 2020 and 2023, generating 48 terabytes of public-domain FITS images stored in the National Astronomical Data Center.""",

    """CHAPTER 5: CURRENT RESEARCH INITIATIVES AND ECOLOGICAL PRESERVATION
Today, the observatory campus spans 140 acres of preserved deciduous teak and bamboo woodland. The buffer zone serves as a micro-sanctuary for endemic avian species, including the Indian Grey Hornbill and the Crested Serpent Eagle. Light pollution regulations enacted by the local district administration in 2012 designated a 15-kilometer radius around the dome as an Astronomical Dark Sky Zone, capping outdoor lighting luminance and requiring fully shielded low-pressure sodium fixtures.

Key historical parameters summary:
- Founding Year: 1974
- Founders: Dr. Anandamurthy Kulkarni and Professor Sneha Deshmukh
- Location: Vindhyachal plateau, latitude 23.4128 N, longitude 77.7214 E, elevation 742 meters
- Primary Instruments: Surya-70 Solar Spectrograph, Vindhya-120 Cassegrain Reflector (1.2m), Rohini Wide-Field Schmidt Camera (85cm corrector)
- Student Fellowship Program: Winter Scholar Fellowship Program (WSFP), 1,264 graduates (1978-1998)
- Clean Energy Microgrid: 150 kW solar PV system commissioned in 2003
- Dark Sky Radius: 15 kilometers designated in 2012
"""
]
full_long_text = "\n\n".join(long_synthetic_text_blocks)
assert len(full_long_text) >= 6000, f"Long text length {len(full_long_text)} < 6000"

summary_cases = [
    {
        "id": "STU-SUM-01",
        "family": "student-summary-v1",
        "complexity": 3,
        "prompt": f"Read the following historical document regarding the Udayagiri Observatory and provide a concise summary covering: (1) Founding year and co-founders, (2) Geographical location and elevation, (3) The three primary instruments, and (4) The clean energy conversion.\n\nDOCUMENT:\n{full_long_text}",
        "ref": "The Udayagiri High-Altitude Solar and Astronomical Research Facility was founded in 1974 by Dr. Anandamurthy Kulkarni and Professor Sneha Deshmukh. It is situated on the Vindhyachal plateau at latitude 23.4128 N, longitude 77.7214 E, at an elevation of 742 meters above sea level. Its three primary historical instruments were the Surya-70 Solar Spectrograph, the Vindhya-120 Cassegrain Reflector (1.2m), and the Rohini Wide-Field Schmidt Camera. In 2003, the facility installed a 150 kW solar photovoltaic microgrid to achieve energy independence and prevent detector interruptions.",
        "check_type": "keywords",
        "keywords": ["1974", "Kulkarni", "Deshmukh", "Vindhyachal", "742", "Surya-70", "Vindhya-120", "Rohini", "150", "solar"],
    },
    {
        "id": "STU-SUM-02",
        "family": "student-summary-v1",
        "complexity": 2,
        "prompt": "Summarize the following passage about the Indian Monsoon in 3 bullet points, highlighting the summer monsoon mechanism, agricultural importance, and rainfall distribution:\n\nPassage: The Indian monsoon is a seasonal wind reversal that brings vital precipitation to the South Asian subcontinent. During summer (June to September), intense heating over the Tibetan Plateau and northwestern plains creates a low-pressure zone that draws moisture-laden winds from the Indian Ocean. Known as the Southwest Monsoon, this system accounts for over 70% of India's annual rainfall and is crucial for Kharif crops such as rice, pulses, and sugarcane. The Western Ghats and northeastern states receive exceptionally heavy precipitation exceeding 2,500 mm annually, whereas the Thar desert receives sparse rainfall.",
        "ref": "- Mechanism: Summer heating creates a low-pressure area drawing moist Southwest Monsoon winds from the Indian Ocean between June and September.\n- Agriculture: Supplies over 70% of annual rainfall essential for Kharif crops like rice, pulses, and sugarcane.\n- Distribution: Rainfall is uneven, with Western Ghats and Northeast receiving over 2,500 mm while the Thar desert remains arid.",
        "check_type": "keywords",
        "keywords": ["southwest monsoon", "kharif", "70%", "indian ocean", "rainfall"],
    },
    {
        "id": "STU-SUM-03",
        "family": "student-summary-v1",
        "complexity": 2,
        "prompt": "Provide a 2-sentence executive summary of the following student library policy:\n\nPolicy: Registered college students may borrow up to four books simultaneously for a duration of fourteen calendar days. Overdue items incur a fine of two rupees per day per book up to a maximum ceiling of one hundred rupees. Reference volumes, periodicals, and rare manuscript archives are strictly non-circulating and must be consulted within the designated reading hall during staffed operating hours.",
        "ref": "Students can borrow up to four books for fourteen days, with late returns fined at two rupees per day up to a hundred rupees. Reference books and rare manuscripts cannot be taken out and must be used inside the reading hall.",
        "check_type": "keywords",
        "keywords": ["four books", "fourteen", "fine", "reading hall"],
    },
]

all_raw_cases = []
# Tag mapping to registry score keys: code, maths, study, hindi, mixed, summary
for c in code_cases:
    c["category"] = "code"
    c["domain"] = "automation"
    c["language"] = "en"
    all_raw_cases.append(c)

for c in maths_cases:
    c["category"] = "maths"
    c["domain"] = "tabular_analysis"
    c["language"] = "en"
    all_raw_cases.append(c)

for c in study_cases:
    c["category"] = "study"
    c["domain"] = "source_reasoning"
    c["language"] = "en"
    all_raw_cases.append(c)

for c in hindi_cases:
    c["category"] = "hindi"
    c["domain"] = "multilingual"
    c["language"] = "hi"
    all_raw_cases.append(c)

for c in mixed_cases:
    c["category"] = "mixed"
    c["domain"] = "multilingual"
    c["language"] = "hi-en"
    all_raw_cases.append(c)

for c in summary_cases:
    c["category"] = "summary"
    c["domain"] = "document_extraction"
    c["language"] = "en"
    all_raw_cases.append(c)

assert len(all_raw_cases) == 49, f"Total cases {len(all_raw_cases)} != 49"

# Assign splits: 31 train, 9 calibration, 9 holdout
# Distribute each category evenly across train/calibration/holdout
by_cat = {}
for c in all_raw_cases:
    by_cat.setdefault(c["category"], []).append(c)

train_cases = []
calib_cases = []
holdout_cases = []

for _cat, items in by_cat.items():
    n = len(items)
    # e.g. for 10: 6 train, 2 calib, 2 holdout
    # for 8: 5 train, 1 calib, 2 holdout (or 4, 2, 2)
    # for 3: 1 train, 1 calib, 1 holdout
    if n == 10:
        c_train, c_calib, c_hold = items[:6], items[6:8], items[8:]
    elif n == 8:
        c_train, c_calib, c_hold = items[:6], items[6:7], items[7:]
    elif n == 3:
        c_train, c_calib, c_hold = [items[0]], [items[1]], [items[2]]
    else:
        k = n // 3
        c_train, c_calib, c_hold = items[:n - 2*k], items[n - 2*k : n - k], items[n - k:]
    train_cases.extend(c_train)
    calib_cases.extend(c_calib)
    holdout_cases.extend(c_hold)

for c in train_cases:
    c["split"] = "train"
for c in calib_cases:
    c["split"] = "calibration"
for c in holdout_cases:
    c["split"] = "holdout"

print(f"Splits count: train={len(train_cases)}, calib={len(calib_cases)}, holdout={len(holdout_cases)}, total={len(all_raw_cases)}")

# Construct standard Parakh Case JSON objects
def format_case_json(item: dict) -> dict:
    return {
        "case_id": item["id"],
        "family_id": f"student-{item['category']}-{item['split']}-family-v1",
        "split": item["split"],
        "complexity_level": item["complexity"],
        "domain": item["domain"],
        "language": item["language"],
        "tags": [item["category"], f"complexity_{item['complexity']}"],
        "messages": [
            {"role": "user", "content": item["prompt"]}
        ],
        "evaluation": {
            "method": "rubric",
            "reference_answer": None,
            "rubric": [
                {"criterion": f"Demonstrates high quality {item['category']} understanding", "weight": 1.0}
            ],
            "critical_failures": ["Hallucination or completely inaccurate answer"],
        },
        "fixture_policy": "synthetic_student_task_v1",
        "suite_version": "student-0.1.0",
        "provenance": {
            "origin": "synthetic_authoring",
            "real_personal_data": False,
            "source_uri": "benchmarks_student/cases.jsonl",
            "source_hash": None,
        },
        "limits": {
            "max_output_tokens": 2048 if item["id"] == "STU-SUM-01" else 1024,
            "max_tool_calls": 0,
        },
    }

all_formatted = [format_case_json(c) for c in all_raw_cases]
train_formatted = [format_case_json(c) for c in train_cases]
calib_formatted = [format_case_json(c) for c in calib_cases]
holdout_formatted = [format_case_json(c) for c in holdout_cases]

# Write JSONL files
def write_jsonl(path: Path, items: list[dict]) -> str:
    lines = [json.dumps(item, ensure_ascii=False) for item in items]
    content = "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

cases_hash = write_jsonl(DEST / "cases.jsonl", all_formatted)
train_hash = write_jsonl(DEST / "train.jsonl", train_formatted)
calib_hash = write_jsonl(DEST / "calibration.jsonl", calib_formatted)
holdout_hash = write_jsonl(DEST / "holdout.jsonl", holdout_formatted)

# Also write holdout.sha256 file
(DEST / "holdout.sha256").write_text(f"{holdout_hash}  holdout.jsonl\n", encoding="utf-8")

# Write reference evaluations file (separate file!)
reference_evaluations = {}
for c in all_raw_cases:
    ref_obj = {
        "case_id": c["id"],
        "category": c["category"],
        "split": c["split"],
        "reference_answer": c["ref"],
        "check_type": c["check_type"],
    }
    if "check_code" in c:
        ref_obj["check_code"] = c["check_code"]
    if "expected" in c:
        ref_obj["expected"] = c["expected"]
    if "keywords" in c:
        ref_obj["keywords"] = c["keywords"]
    reference_evaluations[c["id"]] = ref_obj

(DEST / "reference_evaluations.json").write_text(
    json.dumps(reference_evaluations, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

# Write manifest.json
manifest = {
    "suite_version": "student-0.1.0",
    "total_cases": len(all_raw_cases),
    "category_counts": {cat: len(items) for cat, items in by_cat.items()},
    "splits": {
        "train": len(train_cases),
        "calibration": len(calib_cases),
        "holdout": len(holdout_cases),
    },
    "checksums": {
        "cases.jsonl": cases_hash,
        "train.jsonl": train_hash,
        "calibration.jsonl": calib_hash,
        "holdout.jsonl": holdout_hash,
    },
    "holdout_sha256": holdout_hash,
}
(DEST / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

print(f"Generated successfully. Holdout SHA-256: {holdout_hash}")
