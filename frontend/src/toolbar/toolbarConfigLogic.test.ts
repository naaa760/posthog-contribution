import { expectLogic } from 'kea-test-utils'

import { initKeaTests } from '~/test/init'
import { toolbarConfigLogic } from '~/toolbar/toolbarConfigLogic'

global.fetch = jest.fn(() =>
    Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve([]),
    } as any as Response)
)

describe('toolbar toolbarLogic', () => {
    let logic: ReturnType<typeof toolbarConfigLogic.build>
    let mockPostHog: any

    beforeEach(() => {
        initKeaTests()

        // Mock PostHog client
        mockPostHog = {
            featureFlags: {
                overrideFeatureFlags: jest.fn(),
                reloadFeatureFlags: jest.fn(),
            },
        }

        logic = toolbarConfigLogic({
            apiURL: 'http://localhost',
            posthog: mockPostHog,
        })
        logic.mount()
    })

    it('is not authenticated', () => {
        expectLogic(logic).toMatchValues({ isAuthenticated: false })
    })

    it('clears feature flag overrides on logout', () => {
        expectLogic(logic, () => {
            logic.actions.logout()
        }).toDispatchActions([logic.actionTypes.logout])

        expect(mockPostHog.featureFlags.overrideFeatureFlags).toHaveBeenCalledWith(false)
        expect(mockPostHog.featureFlags.reloadFeatureFlags).toHaveBeenCalled()
    })

    it('clears feature flag overrides on token expiration', () => {
        expectLogic(logic, () => {
            logic.actions.tokenExpired()
        }).toDispatchActions([logic.actionTypes.tokenExpired])

        expect(mockPostHog.featureFlags.overrideFeatureFlags).toHaveBeenCalledWith(false)
        expect(mockPostHog.featureFlags.reloadFeatureFlags).toHaveBeenCalled()
    })

    it('handles logout when posthog client is not available', () => {
        const logicWithoutPostHog = toolbarConfigLogic({
            apiURL: 'http://localhost',
            posthog: null,
        })
        logicWithoutPostHog.mount()

        expectLogic(logicWithoutPostHog, () => {
            logicWithoutPostHog.actions.logout()
        }).toDispatchActions([logicWithoutPostHog.actionTypes.logout])

        // Should not throw an error when posthog is null
        expect(() => logicWithoutPostHog.actions.logout()).not.toThrow()
    })
})
