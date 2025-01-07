import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime
from typing import Any, Dict, List, Optional
from neohub import NeoHub

# Initialize session state
if 'client' not in st.session_state:
    st.session_state.client = None
if 'devices' not in st.session_state:
    st.session_state.devices = None

st.set_page_config(page_title="NeoHub Dashboard", layout="wide")

def login():
    st.session_state.client = NeoHub(
        username=st.session_state.username,
        password=st.session_state.password
    )
    try:
        st.session_state.devices = st.session_state.client.login()
        st.success("Successfully logged in!")
    except Exception as e:
        st.error(f"Login failed: {str(e)}")
        st.session_state.client = None
        st.session_state.devices = None

def style_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply conditional styling to the dataframe."""
    def highlight_row(row):
        styles = []
        for col in row.index:
            if col == 'Status' and any(x in str(row[col]) for x in ['⚠️', '🪟', '🔋']):
                styles.append('background-color: #ffebeb')  # Light red
            elif col == 'Current Temp' and not is_valid_temperature(str(row[col])):
                styles.append('background-color: #ffebeb')  # Light red
            elif col == 'Status' and '🔥' in str(row[col]):
                styles.append('background-color: #e6ffe6')  # Light green
            else:
                styles.append('')
        return styles
    
    return df.style.apply(highlight_row, axis=1)

def get_device_type(zone_data: Any) -> str:
    """Determine if a zone is a thermostat or socket based on its data."""
    # Check for characteristics that indicate a socket
    if (isinstance(zone_data.ACTUAL_TEMP, str) and zone_data.ACTUAL_TEMP == "255.255") or \
       "Socket" in zone_data.ZONE_NAME:
        return "SOCKET"
    return "THERMOSTAT"

def is_valid_temperature(temp_str: str, device_type: str = "THERMOSTAT") -> bool:
    """Check if temperature reading is valid."""
    if device_type == "SOCKET":
        return True  # Sockets don't have valid temperature readings
    try:
        temp = float(temp_str)
        return 0 <= temp <= 50  # Normal range for room temperature
    except (ValueError, TypeError):
        return False

def get_problematic_zones(devices: List[Any]) -> List[Dict[str, str]]:
    """Get list of zones with issues."""
    problems = []
    for device in devices:
        if not device.online:
            problems.append({
                'Device': device.devicename,
                'Zone': 'All Zones',
                'Issue': 'Device Offline'
            })
            continue
        
        try:
            data = st.session_state.client.get_data(device.deviceid)
            zones = data['CACHE_VALUE']['live_info']['devices']
            
            for zone in zones:
                # Determine device type
                device_type = get_device_type(zone)
                
                # Check for invalid temperatures (only for thermostats)
                if device_type == "THERMOSTAT" and not is_valid_temperature(zone.ACTUAL_TEMP, device_type):
                    problems.append({
                        'Device': device.devicename,
                        'Zone': zone.ZONE_NAME,
                        'Issue': f'Invalid Temperature Reading: {zone.ACTUAL_TEMP}'
                    })
                
                # Check for low battery
                if zone.LOW_BATTERY:
                    problems.append({
                        'Device': device.devicename,
                        'Zone': zone.ZONE_NAME,
                        'Issue': 'Low Battery'
                    })
                
                # Check for window open
                if zone.WINDOW_OPEN:
                    problems.append({
                        'Device': device.devicename,
                        'Zone': zone.ZONE_NAME,
                        'Issue': 'Window Open'
                    })
        except Exception as e:
            problems.append({
                'Device': device.devicename,
                'Zone': 'All Zones',
                'Issue': f'Error: {str(e)}'
            })
    
    return problems

# Sidebar for login
with st.sidebar:
    st.title("NeoHub Control")
    if st.session_state.client is None:
        st.subheader("Login")
        st.text_input("Username", key="username", placeholder="Enter your NeoHub email")
        st.text_input("Password", key="password", type="password", placeholder="Enter your password")
        st.button("Login", on_click=login)
    else:
        st.success("Logged in")
        if st.button("Logout"):
            st.session_state.client = None
            st.session_state.devices = None
            st.rerun()

# Main content
if st.session_state.client and st.session_state.devices:
    # Check for problems
    problems = get_problematic_zones(st.session_state.devices)
    if problems:
        st.warning("⚠️ System Warnings")
        problems_df = pd.DataFrame(problems)
        st.dataframe(problems_df, use_container_width=True)
    
    # Tabs for different functionality
    tab1, tab2, tab3, tab4 = st.tabs(["Zone Control", "Matrix View", "Data Export", "System Overview"])
    
    with tab1:
        st.header("Zone Control")
        
        # Device and zone selection
        col1, col2 = st.columns(2)
        with col1:
            selected_device = st.selectbox(
                "Select Device",
                options=[d for d in st.session_state.devices if d.online],
                format_func=lambda x: x.devicename
            )
        
        if selected_device:
            # Get zone data
            data = st.session_state.client.get_data(selected_device.deviceid)
            zones = data['CACHE_VALUE']['live_info']['devices']
            
            with col2:
                selected_zone = st.selectbox(
                    "Select Zone",
                    options=zones,
                    format_func=lambda x: x.ZONE_NAME
                )
            
            if selected_zone:
                device_type = get_device_type(selected_zone)
                # Zone control interface
                st.subheader(f"Zone: {selected_zone.ZONE_NAME} ({device_type})")
                
                if device_type == "SOCKET":
                    st.info("This is a power socket device. Temperature controls are not available.")
                else:
                    cols = st.columns(4)
                    
                    with cols[0]:
                        st.metric("Current Temperature", f"{selected_zone.ACTUAL_TEMP}°C")
                    
                    with cols[1]:
                        # Handle invalid temperature values
                        try:
                            current_temp = float(selected_zone.SET_TEMP)
                            if not is_valid_temperature(str(current_temp)):
                                current_temp = 20.0  # Default to safe temperature
                        except (ValueError, TypeError):
                            current_temp = 20.0
                        
                        new_temp = st.number_input(
                            "Set Temperature",
                            min_value=5.0,
                            max_value=30.0,
                            value=min(max(current_temp, 5.0), 30.0),  # Clamp value to valid range
                            step=0.5
                        )
                        if st.button("Set Temperature"):
                            try:
                                st.session_state.client.set_temperature(
                                    selected_device.deviceid,
                                    selected_zone.ZONE_NAME,
                                    new_temp
                                )
                                st.success("Temperature updated!")
                            except Exception as e:
                                st.error(f"Failed to set temperature: {str(e)}")
                    
                    with cols[2]:
                        mode = st.selectbox(
                            "Mode",
                            options=["HEAT", "COOL", "VENT"],
                            index=0 if selected_zone.HEAT_MODE else 1
                        )
                        if st.button("Set Mode"):
                            try:
                                st.session_state.client.set_mode(
                                    selected_device.deviceid,
                                    selected_zone.ZONE_NAME,
                                    mode
                                )
                                st.success("Mode updated!")
                            except Exception as e:
                                st.error(f"Failed to set mode: {str(e)}")
                    
                    with cols[3]:
                        st.metric("Humidity", f"{selected_zone.RELATIVE_HUMIDITY}%")
                        
                    # Additional zone information
                    with st.expander("Additional Zone Information"):
                        info_cols = st.columns(3)
                        with info_cols[0]:
                            st.write("Status")
                            st.write(f"Heating: {'On' if selected_zone.HEAT_ON else 'Off'}")
                            st.write(f"Window Open: {'Yes' if selected_zone.WINDOW_OPEN else 'No'}")
                            st.write(f"Low Battery: {'Yes' if selected_zone.LOW_BATTERY else 'No'}")
                        
                        with info_cols[1]:
                            st.write("Timer Settings")
                            st.write(f"Timer Active: {'Yes' if selected_zone.TIMER_ON else 'No'}")
                            st.write(f"Profile: {selected_zone.ACTIVE_PROFILE}")
                            st.write(f"Hold Time: {selected_zone.HOLD_TIME}")
                        
                        with info_cols[2]:
                            st.write("System")
                            st.write(f"Mode Lock: {'Yes' if selected_zone.MODELOCK else 'No'}")
                            st.write(f"Floor Limit: {'Yes' if selected_zone.FLOOR_LIMIT else 'No'}")
                            st.write(f"Modulation: {selected_zone.MODULATION_LEVEL}%")

    with tab2:
        st.header("Matrix View")
        
        # Device selection
        selected_devices = st.multiselect(
            "Select Devices to Include",
            options=[d for d in st.session_state.devices if d.online],
            default=[d for d in st.session_state.devices if d.online],
            format_func=lambda x: x.devicename
        )
        
        if selected_devices:
            # Collect all zone data
            matrix_data = []
            for device in selected_devices:
                data = st.session_state.client.get_data(device.deviceid)
                for zone in data['CACHE_VALUE']['live_info']['devices']:
                    status_indicators = []
                    if zone.HEAT_ON:
                        status_indicators.append("🔥")  # Heating
                    if zone.WINDOW_OPEN:
                        status_indicators.append("🪟")  # Window open
                    if zone.LOW_BATTERY:
                        status_indicators.append("🔋")  # Low battery
                    
                    device_type = get_device_type(zone)
                    if device_type == "THERMOSTAT" and not is_valid_temperature(zone.ACTUAL_TEMP, device_type):
                        status_indicators.append("⚠️")  # Invalid reading
                    
                    matrix_data.append({
                        'Device': device.devicename,
                        'Zone': zone.ZONE_NAME,
                        'Type': device_type,
                        'Current Temp': 'N/A' if device_type == "SOCKET" else zone.ACTUAL_TEMP,
                        'Target Temp': 'N/A' if device_type == "SOCKET" else zone.SET_TEMP,
                        'Mode': zone.HC_MODE,
                        'Status': " ".join(status_indicators) if status_indicators else "✓",
                        'Humidity': 'N/A' if device_type == "SOCKET" else f"{zone.RELATIVE_HUMIDITY}%",
                        'Timer': "On" if zone.TIMER_ON else "Off",
                        'Profile': zone.ACTIVE_PROFILE,
                        'Modulation': 'N/A' if device_type == "SOCKET" else f"{zone.MODULATION_LEVEL}%"
                    })
            
            matrix_df = pd.DataFrame(matrix_data)
            
            # Display options
            col1, col2, col3 = st.columns(3)
            with col1:
                sort_by = st.selectbox(
                    "Sort by",
                    options=['Device', 'Zone', 'Type', 'Current Temp', 'Target Temp', 'Mode'],
                    index=0
                )
            with col2:
                show_details = st.checkbox("Show Additional Details", value=False)
            with col3:
                highlight_issues = st.checkbox("Highlight Issues", value=True)
            
            # Filter columns based on detail level
            if show_details:
                display_columns = matrix_df.columns
            else:
                display_columns = ['Device', 'Zone', 'Type', 'Current Temp', 'Target Temp', 'Mode', 'Status']
            
            # Sort the dataframe
            matrix_df = matrix_df.sort_values(by=sort_by)
            
            # Display the matrix with conditional styling
            if highlight_issues:
                styled_df = style_dataframe(matrix_df[display_columns])
            else:
                styled_df = matrix_df[display_columns]
            
            st.dataframe(styled_df, use_container_width=True, height=400)
            
            # Export options
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Export Matrix to CSV"):
                    csv = matrix_df.to_csv(index=False)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"neohub_matrix_{timestamp}.csv"
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=filename,
                        mime="text/csv"
                    )
            
            with col2:
                if st.button("Export Matrix to Excel"):
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                        matrix_df.to_excel(writer, index=False)
                        worksheet = writer.sheets['Sheet1']
                        
                        # Auto-adjust column widths
                        for idx, col in enumerate(matrix_df.columns):
                            max_length = max(
                                matrix_df[col].astype(str).apply(len).max(),
                                len(str(col))
                            ) + 2
                            worksheet.set_column(idx, idx, max_length)
                    
                    buffer.seek(0)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"neohub_matrix_{timestamp}.xlsx"
                    st.download_button(
                        label="Download Excel",
                        data=buffer,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            
            # Summary statistics
            st.subheader("Matrix Summary")
            total_zones = len(matrix_df)
            heating_zones = len(matrix_df[matrix_df['Status'].str.contains("🔥")])
            problem_zones = len(matrix_df[matrix_df['Status'].str.contains("⚠️|🪟|🔋")])
            socket_zones = len(matrix_df[matrix_df['Type'] == "SOCKET"])
            
            summary_cols = st.columns(4)
            summary_cols[0].metric("Total Zones", total_zones)
            summary_cols[1].metric("Heating Zones", heating_zones)
            summary_cols[2].metric("Problem Zones", problem_zones)
            summary_cols[3].metric("Socket Zones", socket_zones)
        
        else:
            st.warning("Please select at least one device to view the matrix")

    with tab3:
        st.header("Data Export")
        
        # Device selection for export
        selected_export_device = st.selectbox(
            "Select Device for Export",
            options=[d for d in st.session_state.devices if d.online],
            format_func=lambda x: x.devicename,
            key="export_device"
        )
        
        if selected_export_device:
            data = st.session_state.client.get_data(selected_export_device.deviceid)
            zones = data['CACHE_VALUE']['live_info']['devices']
            
            # Create DataFrame
            records = []
            for zone in zones:
                device_type = get_device_type(zone)
                record = {
                    'Zone': zone.ZONE_NAME,
                    'Type': device_type,
                    'Current Temperature': 'N/A' if device_type == "SOCKET" else zone.ACTUAL_TEMP,
                    'Target Temperature': 'N/A' if device_type == "SOCKET" else zone.SET_TEMP,
                    'Heating': 'On' if zone.HEAT_ON else 'Off',
                    'Mode': zone.HC_MODE,
                    'Humidity': 'N/A' if device_type == "SOCKET" else zone.RELATIVE_HUMIDITY,
                    'Window Open': 'Yes' if zone.WINDOW_OPEN else 'No',
                    'Timer Active': 'Yes' if zone.TIMER_ON else 'No',
                    'Low Battery': 'Yes' if zone.LOW_BATTERY else 'No',
                    'Modulation Level': 'N/A' if device_type == "SOCKET" else zone.MODULATION_LEVEL
                }
                records.append(record)
            
            df = pd.DataFrame(records)
            
            # Display data
            st.dataframe(df)
            
            # Export options
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Export to CSV"):
                    csv = df.to_csv(index=False)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"neohub_export_{selected_export_device.devicename}_{timestamp}.csv"
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=filename,
                        mime="text/csv"
                    )
            
            with col2:
                if st.button("Export to Excel"):
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    buffer.seek(0)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"neohub_export_{selected_export_device.devicename}_{timestamp}.xlsx"
                    st.download_button(
                        label="Download Excel",
                        data=buffer,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
    
    with tab4:
        st.header("System Overview")
        
        # Summary metrics
        total_devices = len(st.session_state.devices)
        online_devices = len([d for d in st.session_state.devices if d.online])
        
        metrics_cols = st.columns(4)
        metrics_cols[0].metric("Total Devices", total_devices)
        metrics_cols[1].metric("Online Devices", online_devices)
        
        # Device status table
        st.subheader("Device Status")
        device_data = []
        for device in st.session_state.devices:
            if device.online:
                data = st.session_state.client.get_data(device.deviceid)
                zones = data['CACHE_VALUE']['live_info']['devices']
                active_zones = len([z for z in zones if z.HEAT_ON])
                total_zones = len(zones)
                socket_zones = len([z for z in zones if get_device_type(z) == "SOCKET"])
                device_data.append({
                    'Device Name': device.devicename,
                    'Status': 'Online' if device.online else 'Offline',
                    'Total Zones': total_zones,
                    'Active Zones': active_zones,
                    'Socket Zones': socket_zones,
                    'Type': device.type,
                    'Version': device.version
                })
        
        device_df = pd.DataFrame(device_data)
        st.dataframe(device_df)
        
        # Temperature overview
        st.subheader("Temperature Overview")
        temp_data = []
        for device in st.session_state.devices:
            if device.online:
                data = st.session_state.client.get_data(device.deviceid)
                for zone in data['CACHE_VALUE']['live_info']['devices']:
                    # Only include thermostat readings
                    device_type = get_device_type(zone)
                    if device_type == "THERMOSTAT" and is_valid_temperature(zone.ACTUAL_TEMP, device_type) and is_valid_temperature(zone.SET_TEMP, device_type):
                        temp_data.append({
                            'Device': device.devicename,
                            'Zone': zone.ZONE_NAME,
                            'Current Temperature': float(zone.ACTUAL_TEMP),
                            'Target Temperature': float(zone.SET_TEMP),
                            'Status': 'Heating' if zone.HEAT_ON else 'Off',
                            'Mode': zone.HC_MODE
                        })
        
        if temp_data:
            temp_df = pd.DataFrame(temp_data)
            
            # Temperature plot
            fig = px.scatter(temp_df, 
                           x='Current Temperature',
                           y='Target Temperature',
                           color='Device',
                           symbol='Status',
                           hover_data=['Zone', 'Mode'],
                           title='Temperature Overview by Zone',
                           labels={
                               'Current Temperature': 'Current Temperature (°C)',
                               'Target Temperature': 'Target Temperature (°C)'
                           })
            
            # Add reference line for equal temperatures
            fig.add_scatter(x=[0, 50], y=[0, 50], mode='lines', 
                          line=dict(dash='dash', color='gray'), 
                          name='Current = Target',
                          hoverinfo='skip')
            
            # Update layout
            fig.update_layout(
                xaxis_range=[0, 35],
                yaxis_range=[0, 35],
                hovermode='closest'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No valid temperature readings available for visualization")

else:
    st.title("Welcome to NeoHub Dashboard")
    st.write("Please login using the sidebar to access your NeoHub devices.")
    
    st.markdown("""
    ### Features
    - **Zone Control**: Control temperature and mode for individual zones
    - **Matrix View**: Overview of all zones with status indicators
    - **Data Export**: Export zone data to CSV or Excel
    - **System Overview**: Device status and temperature visualization
    
    ### Status Indicators
    - 🔥 Heating active
    - 🪟 Window open
    - 🔋 Low battery
    - ⚠️ Invalid reading
    - ✓ Normal operation
    
    ### Device Types
    - **Thermostat**: Temperature control and monitoring
    - **Socket**: Power socket control (no temperature readings)
    """)
