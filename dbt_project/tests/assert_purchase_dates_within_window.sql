/*
    Every order must fall inside the coverage window declared in the project
    vars. An order dated outside it means a parsing or timezone error, not a
    genuine early adopter.

    A generous margin is allowed on either side so the test flags impossible
    dates (1970, 2035) rather than the naturally sparse edges of the export,
    which are handled by the is_in_analysis_window flag instead.

    Severity: error.
*/

select
    order_id,
    order_purchase_date,
    order_status
from {{ ref('fct_orders') }}
where order_purchase_date < date_sub(date('{{ var("analysis_start_date") }}'), interval 3 month)
    or order_purchase_date > date_add(date('{{ var("analysis_end_date") }}'), interval 3 month)
