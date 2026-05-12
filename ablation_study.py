import torch
import torch._inductor.config

# --- PYTORCH COMPATIBILITY PATCH (same as your server) ---
for i in range(1, 8):
    if not hasattr(torch, f"int{i}"):
        setattr(torch, f"int{i}", torch.int8)

if not hasattr(torch.nn.Module, "set_submodule"):
    def set_submodule(self, target, module):
        parts = target.split('.')
        curr = self
        for part in parts[:-1]:
            curr = getattr(curr, part)
        setattr(curr, parts[-1], module)
    torch.nn.Module.set_submodule = set_submodule
# ---------------------------------------------------------

from unsloth import FastLanguageModel
from dotenv import load_dotenv
import os
import json
from datetime import datetime

load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")

# ============================================================
#  CONFIGURATION — edit these before running
# ============================================================

FINETUNED_MODEL = "gelogabs123/java-teacher-qwen-7b-lora-v3"
BASE_MODEL      = "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit"
MAX_SEQ_LENGTH  = 4096
MAX_NEW_TOKENS  = 512

# Add as many test cases as you like.
# Each entry needs a "task" and a "code" field.
TEST_CASES = [
    {
        "name": "student1-first-answer",
        "task": """
Exercise 2.2 File Management
Write a Java program that opens a program file readonly (any text files) and prints it out to
stdout. Each line printed should have a line number added to i
""",
        "code": """
import java.io.File;

public class Answer {
    public static void main(String[] args) {

        File file = new File("example.txt");

        int lineNumber = 1;

        System.out.println(lineNumber + ": " + file);

        lineNumber++;
        System.out.println(lineNumber + ": " + file);
    }
}
"""
    },
    {
        "name": "student7-first-answer",
        "task": """
Exercise 2.2 File Management
Write a Java program that opens a program file readonly (any text files) and prints it out to
stdout. Each line printed should have a line number added to i
""",
        "code": """
import java.io.*;

public class Main {
    public static void main(String[] args) throws Exception {

        // opening the file again and again for no reason
        File file = new File("file.txt");

        int number = 1;

        // pointless loop just to make it worse
        for (int i = 0; i < 1000; i++) {

            BufferedReader reader = new BufferedReader(new FileReader(file));

            String line = "";

            // bad loop condition (will skip last line sometimes)
            while (line != null) {

                line = reader.readLine();

                // prints even when line is null (so you'll get "null" printed)
                System.out.println(number + " -> " + line);

                // incrementing randomly
                number = number + i;

                // unnecessary break that makes no sense
                if (number % 7 == 0) {
                    break;
                }
            }

            // never closing reader properly (memory leak vibes)
        }

        // useless print at the end
        System.out.println("done maybe?");
    }
}
"""
    },
    {
        "name": "student",
        "task": """
Exercise 2.2 File Management
Write a Java program that opens a program file readonly (any text files) and prints it out to
stdout. Each line printed should have a line number added to i
""",
        "code": """
pimport java.io.File;                  // Import the File class
import java.io.FileNotFoundException; // Import this class to handle errors
import java.util.Scanner;             // Import the Scanner class to read text files

public class ReadFile {
  public static void main(String[] args) {

    String filename = "filename.txt";

    if (args.length > 0) {
      filename = args[0]; // Use the first command-line argument as the filename
    }

    File myFileObject = new File(filename);

    // try-with-resources: Scanner will be closed automatically
    try (Scanner myReader = new Scanner(myFileObject)) {
      int lineCount = 0; 
      while (myReader.hasNextLine()) {
        String data = myReader.nextLine();
        System.out.println("Line " + (lineCount + 1) + ": " + data);
        lineCount++;
      }
    } catch (FileNotFoundException e) {
      System.out.println("An error occurred.");
      e.printStackTrace();
    }
  }
}
"""
    },
]

# ============================================================
#  PROMPT BUILDER — must match your training template exactly
# ============================================================

def build_prompt(task: str, code: str) -> str:
    return f"""You are an expert Computer Science Instructor. Grade the following Java assignment.

### TASK:
{task}

### STUDENT SUBMISSION:
{code}

### FEEDBACK:\n"""


# ============================================================
#  INFERENCE FUNCTION
# ============================================================

def get_feedback(model, tokenizer, task: str, code: str) -> str:
    prompt = build_prompt(task, code)
    inputs = tokenizer([prompt], return_tensors="pt").to("cuda")
    outputs = model.generate(
        **inputs,
        max_new_tokens=MAX_NEW_TOKENS,
        use_cache=True
    )
    response = tokenizer.batch_decode(outputs)[0]
    feedback = response.split("### FEEDBACK:\n")[-1].replace(tokenizer.eos_token, "").strip()
    return feedback


# ============================================================
#  LOAD MODEL HELPER
# ============================================================

def load_model(model_name: str):
    print(f"\n{'='*60}")
    print(f"  Loading: {model_name}")
    print(f"{'='*60}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
        token=HF_TOKEN,
    )
    FastLanguageModel.for_inference(model)
    return model, tokenizer


# ============================================================
#  MAIN — runs all test cases for both models and saves output
# ============================================================

def main():
    results = []

    # Fine-tuned feedback already exists in GitHub from the user study.
    # We only need to run the base model here, then manually compare
    # its output against the real feedback stored in your feedback repos.
    print("\n>>> Running Base Model for Ablation Comparison")
    base_model, base_tokenizer = load_model(BASE_MODEL)

    for tc in TEST_CASES:
        print(f"\n  Running test case: {tc['name']}...")
        feedback = get_feedback(base_model, base_tokenizer, tc["task"], tc["code"])
        results.append({
            "test_case":      tc["name"],
            "task":           tc["task"],
            "code":           tc["code"],
            "base_feedback":  feedback,
        })
        print(f"  Done.")

    del base_model, base_tokenizer
    torch.cuda.empty_cache()

    # --------------------------------------------------------
    #  SAVE RESULTS
    # --------------------------------------------------------

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Save raw JSON (useful for further analysis)
    json_path = f"ablation_results_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Raw results saved to: {json_path}")

    # 2. Save readable markdown report (easy to paste into your report)
    md_path = f"ablation_results_{timestamp}.md"
    with open(md_path, "w") as f:
        f.write("# Ablation Study: Fine-Tuned vs Base Model\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"**Fine-tuned model:** `{FINETUNED_MODEL}`\n\n")
        f.write(f"**Base model:** `{BASE_MODEL}`\n\n")
        f.write("---\n\n")

        for r in results:
            f.write(f"## Test Case: {r['test_case']}\n\n")
            f.write(f"**Task:** {r['task']}\n\n")
            f.write("**Code submitted:**\n```java\n")
            f.write(r["code"].strip())
            f.write("\n```\n\n")

            f.write("### Base Model Feedback\n\n")
            f.write(r["base_feedback"])
            f.write("\n\n")

            f.write("### Fine-Tuned Model Feedback\n\n")
            f.write("*(Paste the corresponding feedback from your GitHub feedback repository here)*\n\n")

            f.write("---\n\n")

    print(f"  Markdown report saved to: {md_path}")
    print("\n  Ablation study complete!")

    print("\n" + "="*60)
    print("  QUICK PREVIEW — First test case")
    print("="*60)
    print(f"\n  Test: {results[0]['test_case']}")
    print(f"\n  [BASE MODEL]\n{results[0]['base_feedback'][:400]}...")
    print("\n  Compare this against the feedback in your GitHub feedback repo.")


if __name__ == "__main__":
    main()