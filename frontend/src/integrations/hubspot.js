import { useState, useEffect } from 'react';
import {
    Box,
    Button,
    CircularProgress
} from '@mui/material';
import axios from 'axios';

export const HubSpotIntegration = ({ user, org, integrationParams, setIntegrationParams }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [isConnecting, setIsConnecting] = useState(false);

    // Function to open OAuth in a new window
    const handleConnectClick = async () => {
        try {
            setIsConnecting(true);

            const formData = new FormData();
            formData.append('user_id', user);
            formData.append('org_id', org);

            const response = await axios.post(
                'http://localhost:8000/integrations/hubspot/authorize',
                formData
            );

            const authURL = response?.data; 
            console.log('HubSpot authorize URL:', authURL);

            const newWindow = window.open(
                authURL,
                'HubSpot Authorization',
                'width=600,height=600'
            );

            if (!newWindow) {
                setIsConnecting(false);
                alert('Popup blocked. Please allow popups for this site.');
                return;
            }

            const pollTimer = window.setInterval(() => {
                if (!newWindow) {
                    window.clearInterval(pollTimer);
                    return;
                }

                let isClosed = false;

                try {
                    // While on app.hubspot.com this access can be restricted,
                    // so we wrap it in try/catch to avoid noisy warnings/errors.
                    isClosed = newWindow.closed;
                } catch (e) {
                    // Still cross-origin – just wait for the next tick.
                    return;
                }

                if (isClosed) {
                    window.clearInterval(pollTimer);
                    handleWindowClosed();
                }
            }, 500);
        } catch (e) {
            console.error('Error during HubSpot authorize:', e);
            setIsConnecting(false);
            const msg =
                e?.response?.data?.detail ||
                e?.message ||
                'Failed to start HubSpot authorization.';
            alert(msg);
        }
    };

    // Function to handle logic when the oauth window closes
    const handleWindowClosed = async () => {
        try {
            const formData = new FormData();
            formData.append('user_id', user);
            formData.append('org_id', org);

            const response = await axios.post(
                'http://localhost:8000/integrations/hubspot/credentials',
                formData
            );

            const credentials = response.data;
            console.log('HubSpot credentials received:', credentials);

            if (credentials) {
                setIsConnecting(false);
                setIsConnected(true);
                setIntegrationParams(prev => ({
                    ...prev,
                    credentials: credentials,
                    type: 'HubSpot',
                }));
            } else {
                setIsConnecting(false);
                alert('No HubSpot credentials returned from backend.');
            }
        } catch (e) {
            console.error('Error fetching HubSpot credentials:', e);
            setIsConnecting(false);
            const msg =
                e?.response?.data?.detail ||
                e?.message ||
                'Failed to get HubSpot credentials.';
            alert(msg);
        }
    };

    useEffect(() => {
        setIsConnected(!!integrationParams?.credentials && integrationParams?.type === 'HubSpot');
    }, []);

    return (
        <Box sx={{ mt: 2 }}>
            Parameters
            <Box
                display="flex"
                alignItems="center"
                justifyContent="center"
                sx={{ mt: 2 }}
            >
                <Button
                    variant="contained"
                    onClick={isConnected ? () => {} : handleConnectClick}
                    color={isConnected ? 'success' : 'primary'}
                    disabled={isConnecting}
                    style={{
                        pointerEvents: isConnected ? 'none' : 'auto',
                        cursor: isConnected ? 'default' : 'pointer',
                        opacity: isConnected ? 1 : undefined,
                    }}
                >
                    {isConnected
                        ? 'HubSpot Connected'
                        : isConnecting
                        ? <CircularProgress size={20} />
                        : 'Connect to HubSpot'}
                </Button>
            </Box>
        </Box>
    );
};
