"""Build the curated demo question bank from compact, human-reviewed rows.

Each row: subject | difficulty | type | topic | question | correct | 5 wrong.
This script is development-time data preparation; the deployed app reads JSON.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

ROWS = r'''
Electrical|easy|conceptual|Fundamentals|What is the SI unit of electric current?|Ampere|Volt;Ohm;Watt;Coulomb;Farad
Electrical|easy|conceptual|Measurements|Which instrument is designed to measure potential difference?|Voltmeter|Ammeter;Ohmmeter;Wattmeter;Galvanometer;Energy meter
Electrical|easy|conceptual|Circuit laws|Which law expresses the relation V = I × R for an ohmic conductor?|Ohm's law|Coulomb's law;Lenz's law;Faraday's law;Kirchhoff's current law;Joule's law
Electrical|easy|conceptual|DC circuits|In a simple series circuit, which quantity is the same through every component?|Current|Voltage;Resistance;Power;Capacitance;Stored energy
Electrical|easy|application|Resistors|A resistor has bands brown, black, red and gold. What is its nominal resistance?|1 kΩ|10 Ω;100 Ω;10 kΩ;100 kΩ;1 MΩ
Electrical|easy|conceptual|Fundamentals|What is the SI unit of electrical resistance?|Ohm|Ampere;Volt;Farad;Henry;Tesla
Electrical|medium|numerical|Series circuits|Two resistors of 4 Ω and 6 Ω are connected in series. What is the total resistance?|10 Ω|2.4 Ω;24 Ω;1 Ω;5 Ω;12 Ω
Electrical|medium|numerical|Parallel circuits|What is the equivalent resistance of 6 Ω and 3 Ω connected in parallel?|2 Ω|9 Ω;3 Ω;1.5 Ω;18 Ω;4.5 Ω
Electrical|medium|numerical|Ohm's law|A 2 Ω resistor carries 3 A. What voltage is across it?|6 V|1.5 V;5 V;9 V;12 V;18 V
Electrical|medium|numerical|Electrical power|A device draws 2 A from a 12 V supply. What is its electrical power?|24 W|6 W;10 W;14 W;48 W;144 W
Electrical|medium|reasoning|Circuit laws|Kirchhoff's current law follows from conservation of which quantity?|Electric charge|Energy;Mass;Momentum;Power;Magnetic flux
Electrical|medium|application|Power electronics|What is the main electrical conversion performed by a rectifier?|AC to DC|DC to AC;AC to mechanical motion;DC to heat only;DC to optical light;AC to higher-frequency AC
Electrical|hard|numerical|Series circuits|A 2 A current flows through series resistors of 3 Ω and 7 Ω. What source voltage is required?|20 V|5 V;10 V;14 V;40 V;70 V
Electrical|hard|numerical|RC circuits|What is the time constant of a 2 kΩ resistor and 3 µF capacitor in series?|6 ms|0.006 ms;0.6 ms;6 s;60 ms;600 ms
Electrical|hard|numerical|AC circuits|A sinusoidal voltage has a peak value of 20 V. Approximately what is its RMS value?|14.14 V|7.07 V;10 V;20 V;28.28 V;40 V
Electrical|hard|numerical|Energy consumption|A 500 W appliance operates for 2 hours. How much electrical energy does it consume?|1 kWh|0.25 kWh;0.5 kWh;2 kWh;4 kWh;10 kWh
Electrical|hard|reasoning|Three-phase systems|In a balanced star-connected three-phase system, line voltage equals phase voltage multiplied by what?|√3|1/√3;1;2;3;√2
Electrical|hard|reasoning|AC circuits|For a fixed capacitor, what happens to capacitive reactance when frequency doubles?|It becomes half|It doubles;It becomes four times;It remains unchanged;It becomes zero;It becomes one quarter
Chemistry|easy|conceptual|Periodic table|What is the chemical symbol for sodium?|Na|S;Sn;N;Ni;So
Chemistry|easy|conceptual|Atomic structure|The atomic number of an element equals the number of which particles?|Protons|Neutrons;Nucleons;Protons plus neutrons;Valence electrons only;Electron shells
Chemistry|easy|conceptual|Compounds|What is the chemical formula of water?|H₂O|H₂O₂;CO₂;H₃O;H₂;H₂O₃
Chemistry|easy|conceptual|Acids and bases|At 25°C, what is the approximate pH of a neutral aqueous solution?|7|0;1;5;10;14
Chemistry|easy|conceptual|Chemical bonding|What mainly happens to electrons when a covalent bond forms?|They are shared between atoms|They are fully transferred;They are converted into protons;Neutrons are shared;Nuclei are exchanged;They all leave both atoms
Chemistry|easy|conceptual|Molecules|An oxygen molecule written O₂ contains how many oxygen atoms?|2|1;3;4;6;8
Chemistry|medium|numerical|Mole concept|What is the molar mass of CO₂? (C = 12, O = 16 g/mol)|44 g/mol|12 g/mol;16 g/mol;28 g/mol;32 g/mol;48 g/mol
Chemistry|medium|numerical|Solutions|What is the molarity of 0.5 mol of solute in 1 litre of solution?|0.5 M|0.05 M;0.25 M;1 M;2 M;5 M
Chemistry|medium|reasoning|Stoichiometry|In 2H₂ + O₂ → 2H₂O, what is the mole ratio of H₂ to O₂ consumed?|2 : 1|1 : 2;1 : 1;3 : 2;2 : 3;4 : 3
Chemistry|medium|conceptual|Redox|In terms of electron transfer, oxidation means what?|Loss of electrons|Gain of electrons;Gain of neutrons;Loss of protons;Gain of protons;No change in electron count
Chemistry|medium|conceptual|Reaction kinetics|How does a catalyst generally affect the activation energy of a reaction?|It lowers the activation energy|It raises the activation energy;It increases the reaction enthalpy;It is always consumed completely;It changes the equilibrium constant at fixed temperature;It changes the balanced equation
Chemistry|medium|reasoning|Acids and bases|Compared with a solution of pH 4, a solution of pH 3 has approximately how much more H⁺ concentration?|10 times|2 times;100 times;The same;One tenth;1000 times
Chemistry|hard|numerical|Acids and bases|Assuming full dissociation, what is the approximate pH of 0.001 M HCl?|3|1;2;4;7;11
Chemistry|hard|numerical|Solutions|What is the molarity of 0.2 mol NaOH dissolved to make 0.5 L solution?|0.4 M|0.1 M;0.2 M;0.5 M;1 M;2 M
Chemistry|hard|reasoning|Oxidation numbers|What is the oxidation state of Mn in KMnO₄?|+7|+2;+4;+5;+6;+8
Chemistry|hard|numerical|Electrochemistry|How many electrons does one Cu²⁺ ion gain to become a neutral Cu atom?|2|0;1;3;4;6
Chemistry|hard|numerical|Stoichiometry|CaCO₃ → CaO + CO₂. Roughly how much CO₂ forms from 10 g CaCO₃? (Molar masses: 100 and 44 g/mol)|4.4 g|1.1 g;2.2 g;5.6 g;8.8 g;10 g
Chemistry|hard|reasoning|Chemical equilibrium|At constant temperature, adding a reactant to a simple equilibrium mixture generally shifts the equilibrium in which direction?|Toward products|Toward reactants;There is no shift;The equilibrium constant increases;The equilibrium constant decreases;The reaction permanently stops
Physics|easy|conceptual|Forces|What is the SI unit of force?|Newton|Joule;Watt;Pascal;Kilogram;Metre
Physics|easy|conceptual|Motion|Average speed equals total distance divided by which quantity?|Total time|Acceleration;Displacement;Mass;Net force;Momentum
Physics|easy|conceptual|Gravity|Near Earth's surface, gravitational acceleration is approximately what?|9.8 m/s²|0.98 m/s²;4.9 m/s²;19.6 m/s²;98 m/s²;9.8 m/s
Physics|easy|conceptual|Energy|Which expression gives translational kinetic energy?|½mv²|mgh;mv;ma;½kx;mc²
Physics|easy|conceptual|Work and power|What is the SI unit of power?|Watt|Joule;Newton;Pascal;Coulomb;Tesla
Physics|easy|conceptual|Newton's laws|Which law describes inertia?|Newton's first law|Newton's second law;Newton's third law;Kepler's second law;Hooke's law;Snell's law
Physics|medium|numerical|Newton's laws|A 2 kg object accelerates at 3 m/s². What is the net force?|6 N|1.5 N;3 N;5 N;9 N;12 N
Physics|medium|numerical|Kinematics|An object starts from rest and accelerates at 2 m/s² for 5 s. What is its final speed?|10 m/s|2.5 m/s;5 m/s;7 m/s;20 m/s;25 m/s
Physics|medium|numerical|Density|A sample has mass 500 g and volume 250 cm³. What is its density?|2 g/cm³|0.5 g/cm³;1 g/cm³;4 g/cm³;5 g/cm³;10 g/cm³
Physics|medium|numerical|Waves|A wave has frequency 50 Hz and wavelength 2 m. What is its speed?|100 m/s|25 m/s;50 m/s;52 m/s;200 m/s;250 m/s
Physics|medium|numerical|Motion|A car travels 100 m in 20 s at steady speed. What is its speed?|5 m/s|2 m/s;4 m/s;10 m/s;20 m/s;80 m/s
Physics|medium|numerical|Work and power|A 10 N force acts parallel to a displacement of 3 m. What work is done?|30 J|3 J;7 J;10 J;13 J;300 J
Physics|hard|reasoning|Projectiles|On level ground with no air resistance, which launch angle gives maximum range at fixed launch speed?|45°|15°;30°;60°;75°;90°
Physics|hard|reasoning|Energy|If an object's speed doubles while mass stays fixed, its kinetic energy becomes what?|Four times as large|Half as large;Twice as large;Three times as large;Eight times as large;Unchanged
Physics|hard|numerical|Momentum|A 2 kg body moving at 3 m/s sticks to a stationary 1 kg body. What is their common speed afterward?|2 m/s|0.5 m/s;1 m/s;1.5 m/s;3 m/s;6 m/s
Physics|hard|reasoning|Circular motion|For uniform circular motion, what is the magnitude of centripetal acceleration?|v²/r|v/r;vr;v²r;r²/v;2πr
Physics|hard|reasoning|Oscillations|In simple harmonic motion, where is speed maximum?|At the equilibrium position|At either turning point;Only at the positive extreme;Only at the negative extreme;At every position equally;Only when acceleration is maximum
Physics|hard|reasoning|Optics|A real object placed at 2f in front of a thin converging lens forms an image that is what?|Real, inverted and equal in size|Virtual, upright and enlarged;Real, upright and smaller;Virtual, inverted and equal in size;Real, inverted and twice as large;No image is formed
Mathematics|easy|numerical|Arithmetic|What is 12 multiplied by 8?|96|20;84;88;104;108
Mathematics|easy|conceptual|Number theory|Which of the following is a prime number?|29|21;27;33;35;39
Mathematics|easy|numerical|Roots|What is the positive square root of 144?|12|10;11;13;14;16
Mathematics|easy|numerical|Percentages|What is 25% of 80?|20|15;16;25;30;40
Mathematics|easy|numerical|Pythagoras|What is 3² + 4²?|25|7;12;24;36;49
Mathematics|easy|numerical|Statistics|What is the arithmetic mean of 2, 4 and 6?|4|3;5;6;8;12
Mathematics|medium|numerical|Algebra|Solve 3x + 5 = 20. What is x?|5|3;4;6;7;15
Mathematics|medium|numerical|Number theory|What is the least common multiple of 12 and 18?|36|6;18;24;54;72
Mathematics|medium|conceptual|Calculus|What is the derivative of x² with respect to x?|2x|x;x²;2;x³;2x²
Mathematics|medium|reasoning|Probability|What is the probability of rolling an even number on a fair six-sided die?|1/2|1/6;1/3;2/3;5/6;1
Mathematics|medium|numerical|Geometry|What is the area of a triangle with base 8 and perpendicular height 5?|20 square units|13 square units;16 square units;25 square units;40 square units;80 square units
Mathematics|medium|numerical|Exponents|What is 2 to the power of 5?|32|10;16;25;64;128
Mathematics|hard|numerical|Integration|What is the definite integral of x² from x = 0 to x = 1?|1/3|1/2;1;2/3;2;3
Mathematics|hard|numerical|Matrices|What is the determinant of the matrix with rows [2, 3] and [1, 4]?|5|2;4;7;8;11
Mathematics|hard|reasoning|Probability|If independent events A and B have P(A) = 0.4, what is P(A given B) when P(B)>0?|0.4|0.16;0.2;0.6;0.8;1
Mathematics|hard|numerical|Quadratics|What are the roots of x² − 5x + 6 = 0?|2 and 3|1 and 6;−2 and −3;−1 and −6;1 and 5;3 and 6
Mathematics|hard|conceptual|Limits|What is the limit of sin(x)/x as x approaches zero, with x in radians?|1|0;−1;1/2;2;Undefined
Mathematics|hard|numerical|Logarithms|What is log base 2 of 32?|5|2;3;4;6;8
Computer Science|easy|conceptual|Computer basics|What does CPU stand for?|Central Processing Unit|Computer Processing Utility;Central Program Unit;Control Processing User;Core Power Unit;Computer Program Utility
Computer Science|easy|numerical|Number systems|What is binary 101 in decimal?|5|3;4;6;7;10
Computer Science|easy|conceptual|Web fundamentals|What does HTML stand for?|HyperText Markup Language|HighText Machine Language;HyperTransfer Markup Language;Home Tool Markup Language;HyperText Markdown Language;High Transfer Machine Logic
Computer Science|easy|conceptual|Data representation|How many bits are in one byte?|8|2;4;6;10;16
Computer Science|easy|conceptual|Databases|What is the primary purpose of a relational table's primary key?|Uniquely identify each row|Automatically encrypt all fields;Sort all query results;Store image files;Remove every duplicate value in the database;Calculate table size
Computer Science|easy|conceptual|Python|Which pair of brackets creates an empty list in Python?|[]|{};();<>;//;set()
Computer Science|medium|conceptual|Algorithms|What is the time complexity of binary search on a sorted array?|O(log n)|O(1);O(n);O(n log n);O(n²);O(2ⁿ)
Computer Science|medium|application|SQL|Which SQL function counts the number of rows returned by a query?|COUNT(*)|SUM(*);MAX(*);MIN(*);AVG(*);LENGTH(*)
Computer Science|medium|conceptual|Networking|Which protocol provides reliable ordered byte-stream transport?|TCP|UDP;IP;ICMP;ARP;DNS
Computer Science|medium|conceptual|Data structures|Which data structure uses last-in, first-out access?|Stack|Queue;Linked list in FIFO mode;Priority queue;Binary search tree;Hash table
Computer Science|medium|conceptual|Web fundamentals|Which language primarily styles the appearance of web pages?|CSS|SQL;C;JSON;XML;Bash
Computer Science|medium|application|Web protocols|Which HTTP status code most commonly means a resource was not found?|404|200;201;301;400;500
Computer Science|hard|conceptual|Databases|In ACID transactions, what does the letter I represent?|Isolation|Integrity;Indexing;Idempotence;Iteration;Interoperability
Computer Science|hard|conceptual|Algorithms|What is the worst-case time complexity of traditional quicksort?|O(n²)|O(1);O(log n);O(n);O(n log n);O(2ⁿ)
Computer Science|hard|reasoning|Operating systems|Which condition requires processes to form a cycle of waiting on one another for resources?|Circular wait|Mutual exclusion;Preemption;Resource sharing;Priority inversion;Paging
Computer Science|hard|conceptual|Database design|Which issue does third normal form primarily address in a relation already in second normal form?|Transitive dependencies of non-key attributes|The need for indexes;Unencrypted passwords;Every many-to-many relationship;SQL injection;All possible duplicate records
Computer Science|hard|conceptual|Hash functions|What is a hash collision?|Different inputs produce the same hash value|One input has two different lengths;A hash table is always full;An input is encrypted with two keys;A search has no result;Two identical inputs produce different deterministic hashes
Computer Science|hard|reasoning|Graph algorithms|Which search finds the shortest path in edge count in an unweighted graph?|Breadth-first search|Depth-first search;Selection sort;Binary search;Heap sort;Greedy best-first search
'''


def main():
    out = []
    seen = set()
    for line in ROWS.strip().splitlines():
        parts = [p.strip() for p in line.split('|')]
        if len(parts) != 7:
            raise ValueError(f'Expected seven fields, got {len(parts)} in: {line}')
        subject, diff, qtype, topic, qtext, correct, wrongs = parts
        incorrect = [s.strip() for s in wrongs.split(';')]
        if len(incorrect) < 5 or any(not s for s in incorrect):
            raise ValueError(f'Need at least five distractors: {qtext}')
        if len({x.casefold() for x in [correct, *incorrect]}) != len(incorrect) + 1:
            raise ValueError(f'Duplicate choices: {qtext}')
        if (subject, qtext.lower()) in seen:
            raise ValueError(f'Duplicate question: {qtext}')
        seen.add((subject,qtext.lower()))
        out.append({'subject':subject,'topic':topic,'difficulty':diff,'question_type':qtype,
                    'text':qtext,'correct_option':correct,'wrong_options':incorrect})
    stats = Counter((q['subject'],q['difficulty']) for q in out)
    print('Total seed questions:',len(out))
    for (subj,diff),n in sorted(stats.items()): print(f'{subj:<18} {diff:<8} {n}')
    dest = Path(__file__).resolve().parent.parent / 'seed' / 'seed_questions.json'
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Wrote',dest)


if __name__ == '__main__':
    main()
