from textual import on
from textual.widgets import DataTable
from textual.events import Mount

class SortableDataTable(DataTable):
    
    def on_mount(self, event: Mount) -> None:
        # We use this to remember if a column is currently sorted Up, Down, or Normal
        self.sort_states = {}

    @on(DataTable.HeaderSelected)
    def handle_column_sort(self, event: DataTable.HeaderSelected) -> None:
        col_key = event.column_key
        
        # Check the current status of this column (asc, desc, or None)
        current_state = self.sort_states.get(col_key, None)

        if current_state is None:
            # 1st Click: Sort Ascending (A-Z)
            self.sort(col_key, reverse=False)
            self.sort_states[col_key] = "asc"
            
        elif current_state == "asc":
            # 2nd Click: Sort Descending (Z-A)
            self.sort(col_key, reverse=True)
            self.sort_states[col_key] = "desc"
            
        else:
            # 3rd Click: Reset State 
            # Note: Textual handles resetting by removing our custom state
            self.sort_states[col_key] = None