from django.db import models

class Contract(models.Model):
    # Matches DB: SERIAL PRIMARY KEY -> IntegerField
    contract_id = models.IntegerField(primary_key=True) 
    
    # --- FIX 1: Change to CharField(42) for Ethereum Addresses ---
    # The addresses are 42 characters long (0x + 40 hex digits)
    buyer_address = models.CharField(max_length=42) 
    seller_address = models.CharField(max_length=42) 
    # ------------------------------------------------------------
    
    # Matches DB: VARCHAR(100)
    product_name = models.CharField(max_length=100) 
    # Matches DB: INT
    quantity = models.IntegerField() 
    # Matches DB: NUMERIC(12,2)
    price = models.DecimalField(max_digits=12, decimal_places=2) 
    
    # Matches DB: TIMESTAMP
    start_date = models.DateTimeField() 
    # Matches DB: TIMESTAMP
    end_date = models.DateTimeField()
    
    # Matches DB: VARCHAR(255). 42 is sufficient, but 255 is fine.
    contract_address = models.CharField(max_length=42, default='0x') 
    
    # NEW FIELD: Uses Django's JSONField, which maps to PostgreSQL's JSONB type
    contract_abi = models.JSONField(default=dict) 
    temperature_threshold = models.FloatField(default=-8)
    
    # Matches DB: VARCHAR(50). Default should match your DB if possible, but 'active' works for filtering.
    status = models.CharField(max_length=50, default='active') 


    class Meta:
        # Crucial: Link to your existing Supabase table name
        db_table = 'contracts' 
        managed = False
