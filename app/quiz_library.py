"""Ready-made quizzes that `flask add-quizzes` gives a quiz master as drafts.

Each quiz is a dict with title, description, category, difficulty and rounds.
A round is a list of (question, options, index of the correct option).
"""

QUIZ_LIBRARY = [
    {
        "title": "General Knowledge",
        "description": "A lively general knowledge challenge.",
        "category": "General",
        "difficulty": "easy",
        "rounds": [
            [  # Science
                ("Which planet is known as the Red Planet?", ["Venus", "Mars", "Jupiter", "Saturn"], 1),
                ("What gas do plants absorb from the atmosphere?", ["Oxygen", "Nitrogen", "Carbon dioxide", "Helium"], 2),
                ("Which organ pumps blood around the body?", ["Lungs", "Heart", "Liver", "Kidney"], 1),
                ("Which element has the chemical symbol O?", ["Gold", "Oxygen", "Osmium", "Argon"], 1),
                ("What is the freezing point of water in Celsius?", ["0", "10", "-10", "100"], 0),
            ],
            [  # History
                (
                    "Who was the first President of the United States?",
                    ["Benjamin Franklin", "Thomas Jefferson", "George Washington", "John Adams"],
                    2,
                ),
                ("Which ancient civilization built Machu Picchu?", ["Romans", "Maya", "Inca", "Greeks"], 2),
                ("The Great Fire of London happened in which year?", ["1663", "1665", "1666", "1668"], 2),
                ("Who discovered penicillin?", ["Marie Curie", "Alexander Fleming", "Isaac Newton", "Albert Einstein"], 1),
                ("Which empire built the Colosseum?", ["Roman Empire", "Ottoman Empire", "Mongol Empire", "British Empire"], 0),
            ],
            [  # Sports
                ("How many players are on a standard soccer team on the field?", ["9", "10", "11", "12"], 2),
                ("In tennis, what is the term for a score of zero?", ["Love", "Draw", "Nil", "Blank"], 0),
                ("Which country hosted the 2016 Summer Olympics?", ["China", "Brazil", "Japan", "Greece"], 1),
                ("Which sport uses the terms 'love', 'deuce', and 'advantage'?", ["Cricket", "Tennis", "Golf", "Basketball"], 1),
                ("How many points is a touchdown worth in American football?", ["3", "6", "7", "8"], 1),
            ],
        ],
    },
    {
        "title": "Around the World",
        "description": "Capitals, oceans, mountains and deserts.",
        "category": "Geography",
        "difficulty": "medium",
        "rounds": [
            [  # Capitals
                ("What is the capital of Australia?", ["Sydney", "Melbourne", "Canberra", "Perth"], 2),
                ("What is the capital of Canada?", ["Toronto", "Ottawa", "Vancouver", "Montreal"], 1),
                ("What is the capital of Japan?", ["Kyoto", "Osaka", "Tokyo", "Hiroshima"], 2),
                ("What is the capital of Brazil?", ["Rio de Janeiro", "São Paulo", "Brasília", "Salvador"], 2),
                ("What is the capital of Turkey?", ["Istanbul", "Ankara", "Izmir", "Antalya"], 1),
            ],
            [  # Planet Earth
                ("Which is the largest ocean?", ["Atlantic", "Indian", "Pacific", "Arctic"], 2),
                ("Which is the highest mountain above sea level?", ["K2", "Kilimanjaro", "Mount Everest", "Mont Blanc"], 2),
                ("Which is the largest hot desert in the world?", ["Gobi", "Sahara", "Kalahari", "Arabian"], 1),
                ("Which continent has the most countries?", ["Asia", "Europe", "Africa", "South America"], 2),
                ("Which country has the largest population?", ["India", "China", "United States", "Indonesia"], 0),
            ],
        ],
    },
    {
        "title": "Africa",
        "description": "Rivers, lakes, capitals and landmarks of the continent.",
        "category": "Geography",
        "difficulty": "easy",
        "rounds": [
            [  # Land and water
                ("What is the longest river in Africa?", ["Congo", "Niger", "Nile", "Zambezi"], 2),
                ("What is the largest lake in Africa?", ["Lake Victoria", "Lake Tanganyika", "Lake Malawi", "Lake Chad"], 0),
                ("What is the highest mountain in Africa?", ["Mount Kenya", "Kilimanjaro", "Mount Stanley", "Mount Elgon"], 1),
                ("What is the largest country in Africa by area?", ["Sudan", "DR Congo", "Algeria", "Libya"], 2),
                (
                    "Which waterfall lies on the Zambezi between Zambia and Zimbabwe?",
                    ["Victoria Falls", "Murchison Falls", "Kalambo Falls", "Tugela Falls"],
                    0,
                ),
            ],
            [  # Countries and capitals
                ("What is the capital of Kenya?", ["Mombasa", "Nairobi", "Kisumu", "Nakuru"], 1),
                ("What is the capital of Uganda?", ["Entebbe", "Jinja", "Kampala", "Gulu"], 2),
                ("What is the capital of Nigeria?", ["Lagos", "Abuja", "Kano", "Ibadan"], 1),
                ("Which country was once called the Gold Coast?", ["Ghana", "Ivory Coast", "Togo", "Sierra Leone"], 0),
                ("Which country has three capital cities?", ["South Africa", "Ethiopia", "Egypt", "Morocco"], 0),
            ],
        ],
    },
    {
        "title": "Science and Nature",
        "description": "From atoms and cells to whales and bees.",
        "category": "Science",
        "difficulty": "medium",
        "rounds": [
            [  # Science
                ("What is the hardest natural substance?", ["Gold", "Iron", "Diamond", "Quartz"], 2),
                ("What is the chemical symbol for sodium?", ["So", "Sd", "Na", "Sn"], 2),
                ("How many bones are in the adult human body?", ["186", "206", "226", "256"], 1),
                ("Roughly how fast does light travel?", ["30,000 km/s", "300,000 km/s", "3,000,000 km/s", "3,000 km/s"], 1),
                ("Which part of a cell holds its genetic material?", ["Nucleus", "Ribosome", "Membrane", "Cytoplasm"], 0),
            ],
            [  # Nature
                ("What is the largest mammal?", ["African elephant", "Blue whale", "Giraffe", "Hippopotamus"], 1),
                ("Which planet is closest to the Sun?", ["Venus", "Mercury", "Earth", "Mars"], 1),
                ("What do bees make honey from?", ["Pollen", "Nectar", "Tree sap", "Water"], 1),
                ("How many legs does a spider have?", ["6", "8", "10", "12"], 1),
                (
                    "What do we call the way plants make food from sunlight?",
                    ["Respiration", "Photosynthesis", "Digestion", "Evaporation"],
                    1,
                ),
            ],
        ],
    },
    {
        "title": "Football Fever",
        "description": "World Cups, clubs and the rules of the beautiful game.",
        "category": "Sports",
        "difficulty": "easy",
        "rounds": [
            [  # Tournaments
                ("Which country has won the most men's World Cups?", ["Germany", "Italy", "Brazil", "Argentina"], 2),
                ("Who won the 2022 World Cup?", ["France", "Argentina", "Croatia", "Morocco"], 1),
                ("Which country hosted the 2010 World Cup?", ["Brazil", "South Africa", "Germany", "Japan"], 1),
                ("Which country has won the most Africa Cup of Nations titles?", ["Egypt", "Cameroon", "Ghana", "Nigeria"], 0),
                ("Which club plays its home games at Old Trafford?", ["Liverpool", "Manchester City", "Manchester United", "Chelsea"], 2),
            ],
            [  # The game
                ("How long is a standard match, not counting added time?", ["80 minutes", "90 minutes", "100 minutes", "120 minutes"], 1),
                ("Which card sends a player off?", ["Yellow", "Red", "Green", "Blue"], 1),
                ("How far is the penalty spot from the goal line?", ["9 metres", "11 metres", "13 metres", "16 metres"], 1),
                ("Which player is nicknamed CR7?", ["Ronaldinho", "Cristiano Ronaldo", "Ronaldo Nazário", "Robinho"], 1),
                ("In which country were the modern rules of football first written?", ["England", "Brazil", "Italy", "Spain"], 0),
            ],
        ],
    },
    {
        "title": "Tech Talk",
        "description": "Computers, the web and the people who built them.",
        "category": "Technology",
        "difficulty": "medium",
        "rounds": [
            [  # Inside the computer
                (
                    "What does CPU stand for?",
                    ["Central Processing Unit", "Computer Personal Unit", "Central Program Utility", "Core Processing Unit"],
                    0,
                ),
                (
                    "What does RAM stand for?",
                    ["Random Access Memory", "Read Access Memory", "Run All Memory", "Rapid Action Memory"],
                    0,
                ),
                ("How many bits are in a byte?", ["4", "8", "16", "32"], 1),
                ("What is the binary number 101 in decimal?", ["3", "5", "6", "101"], 1),
                ("Which of these is an operating system?", ["Linux", "Firefox", "Excel", "Google"], 0),
            ],
            [  # The web and its makers
                (
                    "What does HTML stand for?",
                    ["HyperText Markup Language", "High Tech Modern Language", "HyperText Main Link", "Home Tool Markup Language"],
                    0,
                ),
                ("Which language is mainly used to style web pages?", ["HTML", "CSS", "Python", "SQL"], 1),
                ("Who co-founded Microsoft with Paul Allen?", ["Steve Jobs", "Bill Gates", "Mark Zuckerberg", "Larry Page"], 1),
                ("Which company makes the iPhone?", ["Samsung", "Apple", "Google", "Nokia"], 1),
                ("What does www stand for in a web address?", ["World Wide Web", "Wide World Web", "Web World Wide", "World Web Wide"], 0),
            ],
        ],
    },
    {
        "title": "Through the Ages",
        "description": "Wars, revolutions and turning points in world history.",
        "category": "History",
        "difficulty": "hard",
        "rounds": [
            [  # Ancient to revolutionary
                ("Who was the first Roman emperor?", ["Julius Caesar", "Augustus", "Nero", "Caligula"], 1),
                ("In which year did the French Revolution begin?", ["1776", "1789", "1799", "1815"], 1),
                ("Which country gave the Statue of Liberty to the United States?", ["United Kingdom", "France", "Spain", "Netherlands"], 1),
                ("Which ship sank on its first voyage in 1912?", ["Lusitania", "Titanic", "Britannic", "Mayflower"], 1),
                ("The Treaty of Versailles ended which war?", ["World War I", "World War II", "The Napoleonic Wars", "The Crimean War"], 0),
            ],
            [  # The modern world
                ("In which year did World War II end?", ["1943", "1944", "1945", "1946"], 2),
                ("Who was the first person to walk on the Moon?", ["Buzz Aldrin", "Yuri Gagarin", "Neil Armstrong", "Michael Collins"], 2),
                ("In which year did the Berlin Wall fall?", ["1987", "1989", "1991", "1993"], 1),
                ("Who was the first woman to be UK Prime Minister?", ["Theresa May", "Margaret Thatcher", "Liz Truss", "Indira Gandhi"], 1),
                ("In which year did Nelson Mandela become President of South Africa?", ["1990", "1994", "1999", "1985"], 1),
            ],
        ],
    },
    {
        "title": "Number Crunch",
        "description": "Quick-fire maths for every team.",
        "category": "Maths",
        "difficulty": "easy",
        "rounds": [
            [  # Arithmetic
                ("What is 7 × 8?", ["54", "56", "58", "64"], 1),
                ("What is the square root of 144?", ["11", "12", "13", "14"], 1),
                ("What is 15% of 200?", ["15", "20", "30", "35"], 2),
                ("What is 2 to the power of 5?", ["10", "16", "25", "32"], 3),
                ("What is 1000 ÷ 8?", ["120", "125", "128", "150"], 1),
            ],
            [  # Shapes and numbers
                ("How many sides does a hexagon have?", ["5", "6", "7", "8"], 1),
                ("What do the angles in a triangle add up to?", ["90°", "180°", "270°", "360°"], 1),
                ("What is the next prime number after 7?", ["9", "10", "11", "13"], 2),
                ("How many minutes are in three and a half hours?", ["180", "210", "230", "350"], 1),
                ("Which number does the Roman numeral X stand for?", ["5", "10", "50", "100"], 1),
            ],
        ],
    },
    {
        "title": "Movies and Music",
        "description": "Films, songs and the stars behind them.",
        "category": "Entertainment",
        "difficulty": "easy",
        "rounds": [
            [  # Movies
                ("Which film features the song 'Let It Go'?", ["Moana", "Frozen", "Tangled", "Encanto"], 1),
                ("In The Lion King, what is Simba's father called?", ["Scar", "Mufasa", "Rafiki", "Timon"], 1),
                ("Which school does Harry Potter attend?", ["Hogwarts", "Durmstrang", "Beauxbatons", "Ilvermorny"], 0),
                ("Which superhero is known as the Dark Knight?", ["Superman", "Batman", "Spider-Man", "Iron Man"], 1),
                ("Which film series features Darth Vader?", ["Star Trek", "Star Wars", "Avatar", "Dune"], 1),
            ],
            [  # Music
                ("Who is known as the King of Pop?", ["Elvis Presley", "Michael Jackson", "Prince", "Stevie Wonder"], 1),
                ("Which instrument usually has 88 keys?", ["Guitar", "Piano", "Violin", "Trumpet"], 1),
                ("How many strings does a standard guitar have?", ["4", "5", "6", "7"], 2),
                ("Bob Marley is famous for which kind of music?", ["Jazz", "Reggae", "Rock", "Country"], 1),
                ("Which band recorded 'Hey Jude'?", ["The Beatles", "The Rolling Stones", "Queen", "ABBA"], 0),
            ],
        ],
    },
]
