# Prompt for BDD → IBDD Translation

## Context

You will translate scenarios written in Gherkin format to an intermediate language called IBDD (Intermediate Behavior-Driven Development). IBDD maintains the Given-When-Then structure but adds formal precision through Symbolic Transition Systems (STS).

## 1. IBDD Definition

### Grammar (EBNF):

```
Scenario ::= Given When Then
Given    ::= 'GIVEN' Declaration '[' Guard ']'
Declaration ::= lv1, ..., lvn
Guard    ::= P | Guard '∧' Guard
When     ::= 'WHEN' Switch+
Switch   ::= Interaction '[' Condition ']' Assignment
Interaction ::= g. iv1, ..., ivn
Condition ::= B
Assignment ::= A
Then     ::= 'THEN' Switch* '[' Guard ']'
```

### Key Elements:

- **Local variables (lv)**: Declared in GIVEN, visible throughout the scenario
- **Global variables**: Persistent system state (e.g., SJL = Scheduled Jobs List)
- **Interaction variables (iv)**: Communication between system and environment
- **Gates**:
  - `!` = system output
  - `?` = input from the environment
- **Guards**: Boolean conditions
- **Assignments**: Assignments (var := expression)

### Operators (both Unicode and ASCII forms accepted):

**Logical Operators:**
- AND: `∧` or `&&`
- OR: `∨` or `||`
- NOT: `¬` or `!`

**Comparison Operators:**
- Equal: `=` or `==`
- Not equal: `≠` or `!=`
- Less than: `<`
- Greater than: `>`
- Less or equal: `≤` or `<=`
- Greater or equal: `≥` or `>=`

**Mathematical Operators:**
- Addition: `+`
- Subtraction: `-`
- Multiplication: `*`
- Division: `/`
- Modulo: `%`
- Power: `^`

**IMPORTANT - NOT Supported:**
- String literals with quotes: `"..."` (use identifiers or constants instead)
- Word "not": use `¬` or `!` instead
- Sets with braces: `{...}`
- Time literals: `"14:00"` (use numeric representation or constants)

---

## 2. Translation Examples

### Example 1: Simple Scenario (Only Given with Local Variable)

**Gherkin Scenario:**
```json
{
  "id": 1,
  "domain": "printer",
  "title": "Submit job to printer",
  "given": "a job file",
  "when": "the operator submits the job file using Submission method",
  "then": "the printer appends a new controller job to the scheduled jobs AND the controller job is of type Job type"
}
```

**IBDD Translation (one-line):**
```
GIVEN JF [true] WHEN ?submit.jf,sm [true] JF := jf THEN !append.cj,sjl [cj.type = JT ∧ sjl = SJL ∧ JT = getJobType(SM)] CJ := cj, SJL := add(CJ, SJL) [is_in_list(CJ, SJL) ∧ CJ.type = JT]
```

**IBDD Translation (formatted for readability with \n):**
```
GIVEN JF [true]
WHEN ?submit.jf,sm [true] JF := jf
THEN !append.cj,sjl [cj.type = JT ∧ sjl = SJL ∧ JT = getJobType(SM)] CJ := cj, SJL := add(CJ, SJL)
[is_in_list(CJ, SJL) ∧ CJ.type = JT]
```

**Reasoning:**
- Given: Only declares local variable `JF` (job file), no preconditions → `[true]`
- When: Input gate `?submit` with interaction variables `jf`, `sm`, condition `[true]`, assignment `JF := jf`
- Then: Output gate `!append` with condition and assignment, postcondition verifying inclusion

---

### Example 2: Scenario with Local Variables and Guards

**Gherkin Scenario:**
```json
{
  "id": 2,
  "domain": "printer",
  "title": "Move production job to printed jobs",
  "given": "a controller job is in the scheduled jobs AND the controller job is a production job",
  "when": "the printer starts printing the controller job AND the printer completes printing the controller job",
  "then": "the controller job is in the printed jobs"
}
```

**IBDD Translation (formatted with \n):**
```
GIVEN CJ [is_in_list(CJ, SJL) ∧ CJ.type = Production]
WHEN !printstart.cj [cj.id = CJ.id ∧ cj.state = Printing] CJ.state := cj.state
!printcomplete.cj [cj.id = CJ.id ∧ cj.state = Completed] CJ.state := cj.state, PJL := add(CJ, PJL)
THEN [is_in_list(CJ, PJL)]
```

**Reasoning:**
- Given: Local variable `CJ` with guard verifying: is in `SJL` AND is of type Production
- When: Two sequential switches (!printstart, !printcomplete) each with condition in brackets and assignments
- Then: No switches, only postcondition verifying that `CJ` is in `PJL`

---

### Example 3: Scenario with Only Guard (No Local Variables)

**Gherkin Scenario:**
```json
{
  "id": 3,
  "domain": "printer",
  "title": "Clean up printed jobs on restart",
  "given": "the printer controller is running",
  "when": "the operator restarts the printer controller",
  "then": "the printed jobs clean up is executed"
}
```

**IBDD Translation (formatted with \n):**
```
GIVEN [is_running(CTRL)]
WHEN ?restart [true] true
THEN !cleanup [true] PJL := empty(PJL)
[is_empty(PJL)]
```

**Reasoning:**
- Given: No local variables, only guard verifying controller is running
- When: Input gate `?restart` with condition `[true]` and assignment `true` (no state change)
- Then: Output gate `!cleanup` that clears list, postcondition verifies it's empty

---

### Example 4: Scenario with Multiple Interaction Variables

**Gherkin Scenario:**
```json
{
  "id": 4,
  "domain": "ecommerce",
  "title": "Add product to cart",
  "given": "a product with price and a shopping cart",
  "when": "the user adds the product to the cart with quantity",
  "then": "the cart contains the product AND the total price is updated"
}
```

**IBDD Translation (formatted with \n):**
```
GIVEN P, SC [P.price > 0 ∧ is_valid(SC)]
WHEN ?add_to_cart.p,sc,qty [p.id = P.id ∧ sc.id = SC.id ∧ qty > 0] SC.items := add(p, SC.items), SC.total := SC.total + (p.price * qty)
THEN [is_in_list(P, SC.items) ∧ SC.total = calculate_total(SC.items)]
```

**Reasoning:**
- Given: Two local variables (`P`, `SC`) with guards verifying valid price and valid cart
- When: Gate with multiple interaction variables, condition in brackets, multiple assignments
- Then: No switches, only postcondition verifying product inclusion and correct total update

---

## 3. Input and Output Format

### Input Format:
```json
[
    {
      "id": "<number>",
      "domain": "<domain>",
      "title": "<title>",
      "given": "<initial conditions>",
      "when": "<actions>",
      "then": "<expected results>"
    }
]
```

### Output Format:
```json
[
    {
      "id": "<number>",
      "domain": "<domain>",
      "title": "<title>",
      "given": "<initial conditions>",
      "when": "<actions>",
      "then": "<expected results>",
      "ibdd_representation": "<IBDD translation>"
    }
]
```

---

## 4. Translation Rules

### 4.1 Given Clause
- Identify if there are mentioned local variables ("a job", "a product" → local variables)
- If it only describes system state → only guard, no declaration
- Combine multiple conditions with `∧`
- Guard MUST be in brackets `[...]`

### 4.2 When Clause
- User actions → input gates (`?`)
- System actions → output gates (`!`)
- Multiple actions with "AND" → multiple sequential switches
- Identify interaction variables needed for communication
- **CRITICAL: Each switch MUST have condition in brackets `[...]`**
- Assignments follow the condition

### 4.3 Then Clause
- Verifies final state in postcondition (final guard)
- If there are explicit system actions → switches with output gates
- **Each switch MUST have condition in brackets `[...]`**
- Postcondition (final guard) MUST be in brackets `[...]`

### 4.4 Naming Conventions
- Local variables: Abbreviations in uppercase (CJ, JF, P, SC)
- Global variables: Descriptive in uppercase (SJL, PJL, CTRL)
- Interaction variables: Lowercase, related to local ones (cj, jf, p, sc)
- Gates: Descriptive verbs in lowercase (submit, printstart, add_to_cart)

---

## 5. Final Instruction

Process the input JSON and return the same JSON with the `"ibdd_representation"` field containing your IBDD translation for each scenario.

**IMPORTANT**:
- Do NOT include explanations, comments, or markdown
- ONLY return the resulting JSON
- Maintain exactly the same structure as the input JSON
- **CRITICAL**: Put your IBDD translation in the `"ibdd_representation"` field (overwrite existing value if present)
- Leave the `"notes"` field unchanged if it exists
- The IBDD representation must be a string with line breaks (`\n`)
- **ALL conditions in Switch must be between brackets `[...]`**
- **ALL guards must be between brackets `[...]`**

**CRITICAL FORMATTING RULES:**
1. GIVEN clause: Single line
2. Each WHEN switch: Separate line with format: `<gate>.<vars> [<condition>] <assignment>`
3. Each THEN switch: Separate line with same format
4. Final THEN guard: Separate line with format: `[<postcondition>]`

**Example of correct formatting:**
```
GIVEN CJ [is_in_list(CJ, SJL)]
WHEN !printstart.cj [cj.id = CJ.id] CJ.state := cj.state
!printcomplete.cj [cj.id = CJ.id] CJ.state := cj.state
THEN [is_in_list(CJ, PJL)]
```

**ALWAYS separate each switch with `\n` (newline character in the JSON string)**