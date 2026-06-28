# preprocessor_agent.py
# from agents.utils.document_parser import DocumentParser
from agents.utils.groq_client import GroqClient
import agents.utils.system_prompt as system_prompt
from agents.utils.clause_extractor import ClauseExtractor
import json
import uuid
import PyPDF2
import re
import spacy
import os


class PreprocessorAgent:
    def __init__(self):
        # self.document_parser = DocumentParser()
        # self.text_classifier = TextClassifier()
        self.clause_extractor = ClauseExtractor()
        # self.model_router = MultiModelRouter()
        # self.llm_client = self.model_router.get_client("preprocessor")
        self.llm_client = GroqClient(model_name="llama-3.3-70b-versatile")

    def process_document(self, file_path: str):
        print(f"[DEBUG] Processing document: {file_path}")
        document_id = str(uuid.uuid4())
        
        # --- Start: Inline parse_pdf logic ---
        text = ""
        with open(file_path, "r", encoding="utf-8") as file:
            text = file.read()
        print(f"[DEBUG] Document text length: {len(text)}")

        # inline title-extraction (formerly extract_title)
        lines = text.split("\n")
        title = "Unknown Title"
        title_candidates = []
        
        # Pattern for common legal keywords to identify potential title lines
        keyword_pattern = re.compile(r"\b(?:AGREEMENT|CONTRACT|STATEMENT|FORM|NOTICE|REPORT|PLAN|POLICY|INDEMNITY|DEED|RESOLUTION|CERTIFICATE|SCHEDULE|APPENDIX|AMENDMENT|SUPPLEMENT)\b", re.IGNORECASE)
        # Fallback for simple all-caps titles without specific keywords
        all_caps_pattern = re.compile(r"^[A-Z0-9\s\-()&,./\\]{5,}$")

        for i, line in enumerate(lines[:15]):  # Check first 15 lines for a title
            clean_line = line.strip()
            if not clean_line or len(clean_line) < 5: 
                continue
            
            extracted_title = ""
            score = 0

            # Prioritize lines containing a strong legal keyword
            if keyword_pattern.search(clean_line):
                # Attempt to capture text up to and including the keyword
                # and then clean common prefixes.
                temp_title = clean_line
                temp_title = re.sub(r"^(?:EXHIBIT\s+[\d.]+\s+)?", "", temp_title, flags=re.IGNORECASE).strip()
                # More aggressive removal of known leading company names or common introductory phrases
                temp_title = re.sub(r"^(?:NETWORK\s+1\s+FINANCIAL\s+CORPORATION|PAYMENT\s+DATA\s+SYSTEMS,\s+INC\.|USIO,\s+INC\.|THIS\s+AGREEMENT\s+IS\s+ENTERED\s+INTO\s+BY\s+AND\s+BETWEEN)\s*", "", temp_title, flags=re.IGNORECASE).strip()
                
                # Find the last occurrence of a keyword to get the most relevant part of the title
                last_keyword_match = list(keyword_pattern.finditer(temp_title))
                if last_keyword_match:
                    end_of_last_keyword = last_keyword_match[-1].end()
                    extracted_title = temp_title[:end_of_last_keyword].strip()
                else:
                    extracted_title = temp_title # If no keyword, take the cleaned line

                if extracted_title:
                    score = 10 # High score for keyword-based extraction
                    if clean_line.isupper():
                        score += 2
                    if len(extracted_title.split()) < 8: # Prefer very concise titles
                        score += 1
                    title_candidates.append((extracted_title, score, len(extracted_title)))
                    continue # Move to next line if a strong match is found

            # Fallback to the all-caps pattern if no keyword-based title found
            all_caps_match = all_caps_pattern.search(clean_line)
            if all_caps_match:
                extracted_title = all_caps_match.group(0).strip()
                # Clean up exhibit prefix for all-caps titles too
                extracted_title = re.sub(r"^(?:EXHIBIT\s+[\d.]+\s+)?", "", extracted_title, flags=re.IGNORECASE).strip()
                score = 3 # Moderate score for all caps
                if len(extracted_title.split()) < 6: # Prefer shorter all-caps titles
                    score += 1
                title_candidates.append((extracted_title, score, len(extracted_title)))

        if title_candidates:
            title_candidates.sort(key=lambda x: (-x[1], x[2]))
            title = title_candidates[0][0]

        # Final cleanup for any leftover punctuation or very short non-descriptive titles
        title = re.sub(r"^[\W_]+|[\W_]+$", "", title).strip() # Remove leading/trailing non-alphanumeric
        if len(title.split()) < 2 and title not in ["AGREEMENT", "CONTRACT"]:
            title = "Unknown Title" # If too short and not a strong keyword, reset

        print(f"[DEBUG] Extracted Title: {title}")
        # --- End: Inline parse_pdf logic ---

        # Prepare a concise document sample for LLM processing
        # This helps avoid token limits with very long documents
        document_sample = text
        if len(text) > 4000:  # Adjust this limit as needed
            document_sample = text[:2000] + "\n...\n" + text[-2000:]
        print(f"[DEBUG] LLM document sample length: {len(document_sample)}")

        # Route document processing to model router; expect strict JSON
        llm_response = self.llm_client.query(
            system_prompt=(
                "You are a Pre-processor Agent. Your task is to analyze legal documents. "
                "Return ONLY a strict JSON object. No conversational text, no markdown. "
                "The JSON object must have two top-level keys: 'CLASS' (string) and 'CLAUSES' (list of objects). "
                "The 'CLASS' should be a concise classification of the document type (e.g., 'Affiliate Agreement', 'Employment Contract', 'Service Agreement'). "
                "Each object in the 'CLAUSES' list must have two keys: 'Text' (string) for the full clause text and 'Category' (string) for its type (e.g., 'Definitions', 'Term', 'Governing Law', 'Termination', 'Indemnification'). "
                "If a class or clauses are not clearly identifiable, use 'Unknown' for CLASS and an empty list for CLAUSES. "
                "Ensure the output is a valid JSON string, and nothing else."
            ),
            prompt=document_sample # Use the document_sample here
        )
        print(f"[DEBUG] Raw LLM response: {llm_response[:1000]}...") # Print first 1000 chars of LLM response

        llm_output = {"CLASS": "Unknown", "CLAUSES": []} # Default values
        try:
            # Attempt to parse as JSON directly
            parsed_response = json.loads(llm_response)
            llm_output["CLASS"] = parsed_response.get("CLASS", "Unknown")
            raw_clauses = parsed_response.get("CLAUSES", [])
            if isinstance(raw_clauses, list):
                cleaned_clauses = []
                for clause in raw_clauses:
                    if isinstance(clause, dict) and "Text" in clause and "Category" in clause:
                        cleaned_clauses.append(clause)
                llm_output["CLAUSES"] = cleaned_clauses
                print(f"[DEBUG] Successfully parsed LLM response as JSON.")
        except json.JSONDecodeError:
            print(f"[PreprocessorAgent ERROR] Failed to parse LLM response as JSON. Attempting regex fallback. Raw response: {llm_response[:500]}...")
            # Fallback using regex for CLASS
            class_match = re.search("\"CLASS\"\\s*:\\s*\"([^\"]*)\"|\'CLASS\':\\s*\'([^\']*)\'", llm_response)
            if class_match:
                llm_output["CLASS"] = class_match.group(1) or class_match.group(2)
                print(f'[DEBUG] Regex Fallback - Document Class: {llm_output["CLASS"]}')
            
            # Fallback using regex for CLAUSES (simplified)
            clause_pattern = "\"Text\"\\s*:\\s*\"([^\"]*)\"\\s*,\\s*\"Category\"\\s*:\\s*\"([^\"]*)\""
            clauses_matches = re.findall(clause_pattern, llm_response)
            if clauses_matches:
                llm_output["CLAUSES"] = [{"Text": text, "Category": category} for text, category in clauses_matches]
                print(f'[DEBUG] Regex Fallback - Number of Clauses: {len(llm_output["CLAUSES"])}')
        except Exception as e:
            print(f"[PreprocessorAgent ERROR] An unexpected error occurred during LLM response parsing: {e}")

        document_class = llm_output.get("CLASS", "")
        clause_classes = llm_output.get("CLAUSES", [])
        print(f"[DEBUG] Final Document Class after processing: {document_class}")
        print(f"[DEBUG] Final Number of Important Clauses after processing: {len(clause_classes)}")

        
        # --- Start: Inline extract_entities logic ---
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text)
        entities_list = []
        for ent in doc.ents:
            entities_list.append((ent.text, ent.label_))
        entities = entities_list 
        # --- End: Inline extract_entities logic ---

        # Assuming context_bank is initialized elsewhere or passed to __init__
        # self.context_bank.add_document(document_id, text, {
        #     "title": title,
        #     "document_type": document_class,
        #     "source_file": file_path
        # })

        # self.context_bank.add_entities(document_id, entities)
        # self.context_bank.add_clauses(document_id, clause_classes)


        return {
            "Text Extracted" : text,
            "Document Title": title,
            "Document Class": document_class,
            "Important Clauses": {clause["Text"]: clause["Category"] for clause in clause_classes},
            "Named Entities": entities
        }

if __name__ == "__main__":
    agent = PreprocessorAgent()
    file_path = "Perturbations/modified_ABILITYINC_06_15_2020-EX-4.25-SERVICESAGREEMENT.txt.txt"
    result = agent.process_document(file_path)
    
    # print("Text Extracted:", result["Text Extracted"])
    print("Document Title:", result["Document Title"])
    print("Document Class:", result["Document Class"])
    print("Important Clauses:", result["Important Clauses"])
    print("Named Entities:", result["Named Entities"])

    # Save output to a JSON file in test_outputs
    output_filename = os.path.basename(file_path).replace(".txt", ".json")
    output_path = os.path.join("test_outputs", output_filename)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4)
    print(f"[INFO] Processed output saved to {output_path}")

