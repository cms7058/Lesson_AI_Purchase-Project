"""Keep all generated files and the mail encryption key on the data volume."""
import os
import sys
from pathlib import Path

for directory in ('generated_documents', 'generated_assets', 'private_word_templates', 'private_rfq_attachments', 'private_supplier_invoices'):
    Path(directory).mkdir(parents=True, exist_ok=True)
os.execvp(sys.argv[1], sys.argv[1:])
